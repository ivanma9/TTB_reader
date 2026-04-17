# ttb_eval_builder.py
# Builds an OCR eval set from TTB Public Registry
# using TTB IDs from the Kaggle demo CSV as seed
#
# pip install requests beautifulsoup4 pandas pillow tqdm

import csv
import time
import hashlib
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tqdm import tqdm

BASE_URL = "https://www.ttbonline.gov/colasonline/"
FORM_URL = BASE_URL + "viewColaDetails.do"
OUT_DIR  = Path("ttb_eval")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (research eval build; contact: ivanma819@gmail.com)",
    "Accept": "text/html,application/xhtml+xml",
}

# ttbonline.gov serves only the leaf cert (no intermediate) — curl works via
# AIA fetching but Python/requests does not. Disable verify for this public
# records site; no auth, no secrets.
VERIFY_TLS = False
if not VERIFY_TLS:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 1. Load TTB IDs from the demo CSV ──────────────────────────────────────
def load_ttb_ids(colas_csv: str, product_type: str = "DISTILLED SPIRITS",
                 limit: int = 100) -> list[dict]:
    """
    Load TTB IDs from colas_2018.csv (or colas_2017.csv).
    Filter to desired product_type. Set limit=None for all.
    """
    df = pd.read_csv(colas_csv, low_memory=False)

    # Filter to target beverage type (DISTILLED SPIRITS for M1)
    if product_type:
        df = df[df["PRODUCT_TYPE"].str.upper() == product_type.upper()]

    # Only records that have at least a front image
    if "HAS_FRONT_IMAGE" in df.columns:
        df = df[df["HAS_FRONT_IMAGE"] == True]

    # Skip physical form submissions (no structured label images)
    if "IS_FORM_PHYSICAL" in df.columns:
        df = df[df["IS_FORM_PHYSICAL"] != True]

    # Select ground truth columns we care about
    keep = [
        "TTB_ID", "BRAND_NAME", "PRODUCT_NAME", "CLASS_NAME", "CLASS_ID",
        "ORIGIN_NAME", "APPLICANT_NAME", "ADDRESS_TEXT", "ADDRESS_STATE",
        "OCR_ABV", "OCR_VOLUME", "OCR_VOLUME_UNIT",
        "APPLICATION_STATUS", "APPROVAL_DATE", "PRODUCT_TYPE",
        "HAS_FRONT_IMAGE", "HAS_BACK_IMAGE", "HAS_NECK_IMAGE",
    ]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].dropna(subset=["TTB_ID"])

    if limit:
        df = df.head(limit)

    return df.to_dict("records")


# ── 2. Scrape one COLA: fetch HTML, extract images + structured fields ──────
def scrape_cola(ttb_id: str, session: requests.Session) -> dict | None:
    """
    Fetch the publicFormDisplay page for a TTB ID.
    Returns dict with image_urls list + any fields parseable from HTML.
    """
    params = {"action": "publicFormDisplay", "ttbid": ttb_id}
    try:
        resp = session.get(FORM_URL, params=params, timeout=20, verify=VERIFY_TLS)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [WARN] {ttb_id}: request failed — {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract label image URLs — they appear as <img> inside "AFFIX LABELS" section
    # Typical src pattern: /colasonline/getPublicFormImg.do?ttbid=...&imgseq=0
    image_urls = []
    image_types = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = img.get("alt", "")
        if "getPublicFormImg" in src or "LabelImage" in src or "label" in src.lower():
            full_url = urljoin(BASE_URL, src)
            image_urls.append(full_url)
            image_types.append(alt)

    # Also capture any images with meaningful alts
    if not image_urls:
        for img in soup.find_all("img"):
            src = img.get("src", "")
            alt = img.get("alt", "").lower()
            if any(k in alt for k in ["brand", "front", "back", "neck", "strip"]):
                image_urls.append(urljoin(BASE_URL, src))
                image_types.append(img.get("alt", ""))

    return {
        "ttb_id": ttb_id,
        "html": resp.text,
        "image_urls": image_urls,
        "image_types": image_types,
        "scraped_html_fields": extract_html_fields(soup),
    }


def extract_html_fields(soup: BeautifulSoup) -> dict:
    """Parse key fields out of the form HTML as a cross-check."""
    fields = {}
    text = soup.get_text(" ", strip=True)

    def after(label):
        idx = text.find(label)
        if idx == -1: return None
        snippet = text[idx + len(label):idx + len(label) + 80].strip()
        return snippet.split()[0] if snippet.split() else None

    fields["html_brand_name"] = after("6. BRAND NAME")
    fields["html_fanciful_name"] = after("7. FANCIFUL NAME")
    fields["html_type_of_product"] = after("5. TYPE OF PRODUCT")
    return fields


# ── 3. Download image bytes ─────────────────────────────────────────────────
def download_image(url: str, dest: Path, session: requests.Session) -> bool:
    try:
        resp = session.get(url, timeout=20, stream=True, verify=VERIFY_TLS)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  [WARN] image download failed {url}: {e}")
        return False


# ── 4. Main build loop ──────────────────────────────────────────────────────
def build_eval_set(colas_csv: str, product_type: str = "DISTILLED SPIRITS",
                   limit: int = 100, delay: float = 0.5):
    """
    Full pipeline: load IDs → scrape TTB → download images → write cases.jsonl
    """
    records = load_ttb_ids(colas_csv, product_type=product_type, limit=limit)
    print(f"Loaded {len(records)} {product_type} records from CSV")

    OUT_DIR.mkdir(exist_ok=True)
    images_dir = OUT_DIR / "images"
    images_dir.mkdir(exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    cases = []

    for rec in tqdm(records, desc="Scraping TTB"):
        ttb_id = str(rec["TTB_ID"]).strip()
        result = scrape_cola(ttb_id, session)

        if result is None or not result["image_urls"]:
            # No images found — skip (is_form_physical or image unavailable)
            print(f"  [SKIP] {ttb_id}: no images")
            time.sleep(delay)
            continue

        # Download each image
        # TTB's getPublicFormImg always returns JPEG; force .jpg.
        # Infer panel (front/neck/back/other) from the <img alt> text.
        def _panel(alt: str) -> str:
            a = (alt or "").lower()
            if "brand" in a or "front" in a:
                return "front"
            if "neck" in a:
                return "neck"
            if "back" in a:
                return "back"
            if "strip" in a:
                return "strip"
            return "other"

        local_images = []
        for i, (url, img_type) in enumerate(
            zip(result["image_urls"], result["image_types"])
        ):
            panel = _panel(img_type)
            fname = images_dir / f"{ttb_id}_{i}_{panel}.jpg"
            ok = download_image(url, fname, session)
            if ok:
                local_images.append({
                    "path": str(fname.relative_to(OUT_DIR)),
                    "type": img_type,
                    "panel": panel,
                    "url": url,
                })

        if not local_images:
            continue

        # Build eval case
        case = {
            "ttb_id": ttb_id,
            "images": local_images,
            # Ground truth from CSV (applicant-submitted fields, TTB-approved)
            "ground_truth": {
                "brand_name": rec.get("BRAND_NAME"),
                "product_name": rec.get("PRODUCT_NAME"),        # fanciful name
                "class_name": rec.get("CLASS_NAME"),
                "origin": rec.get("ORIGIN_NAME"),
                "applicant_name": rec.get("APPLICANT_NAME"),
                "address_state": rec.get("ADDRESS_STATE"),
                "product_type": rec.get("PRODUCT_TYPE"),
                "approval_status": rec.get("APPLICATION_STATUS"),
                "approval_date": rec.get("APPROVAL_DATE"),
            },
            # COLA Cloud's OCR extractions — use as reference for ABV/volume eval
            "cola_cloud_ocr_reference": {
                "ocr_abv": rec.get("OCR_ABV"),
                "ocr_volume": rec.get("OCR_VOLUME"),
                "ocr_volume_unit": rec.get("OCR_VOLUME_UNIT"),
            },
            # Panel flags from CSV (tells you which images exist)
            "panels": {
                "has_front": rec.get("HAS_FRONT_IMAGE"),
                "has_back": rec.get("HAS_BACK_IMAGE"),
                "has_neck": rec.get("HAS_NECK_IMAGE"),
            },
            # HTML cross-check fields (scraped, not from CSV)
            "html_crosscheck": result["scraped_html_fields"],
        }
        cases.append(case)
        time.sleep(delay)

    # Write cases.jsonl
    import json
    out_path = OUT_DIR / "cases.jsonl"
    with open(out_path, "w") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")

    # Write summary CSV
    summary_path = OUT_DIR / "summary.csv"
    pd.DataFrame([
        {
            "ttb_id": c["ttb_id"],
            "image_count": len(c["images"]),
            "brand_name": c["ground_truth"]["brand_name"],
            "class_name": c["ground_truth"]["class_name"],
            "ocr_abv_reference": c["cola_cloud_ocr_reference"]["ocr_abv"],
        }
        for c in cases
    ]).to_csv(summary_path, index=False)

    print(f"\nDone. {len(cases)} eval cases written to {out_path}")
    print(f"Summary: {summary_path}")
    return cases


# ── 5. Entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "colas_2018.csv"
    build_eval_set(
        colas_csv=csv_path,
        product_type="DISTILLED SPIRITS",   # change to None for all types
        limit=50,                            # start small
        delay=0.5,                           # be polite to ttbonline.gov
    )
