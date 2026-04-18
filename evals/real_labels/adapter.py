"""Adapter: turn scraped ttb_eval/cases.jsonl into golden-set-schema cases.

Input : ttb_eval/cases.jsonl  (produced by scripts/ttb_eval_builder.py)
Output: evals/real_labels/cases.jsonl (consumed by run_golden_set.py)

Each output case expects a clean_match / accept verdict, since every COLA in
the Kaggle seed is TTB-approved. Any failure on this set is signal that the
verifier misread a real label.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from scripts.label_real_cases import load_corrections as _load_corrections

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "ttb_eval" / "cases.jsonl"
OUTPUT_PATH = ROOT / "evals" / "real_labels" / "cases.jsonl"
CORRECTIONS_PATH = ROOT / "evals" / "real_labels" / "corrections.jsonl"
CORRECTIBLE_FIELDS = ("class_type", "producer_name_address")

CANONICAL_WARNING = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD "
    "NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF "
    "BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR "
    "ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH "
    "PROBLEMS."
)

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
    "puerto rico", "virgin islands",
}


def _pick_front(images: List[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    for img in images:
        if img.get("panel") == "front":
            return img
    return None


def _derive_is_import(origin: Optional[str]) -> bool:
    if not origin:
        return False
    return origin.strip().lower() not in US_STATES


def _title_country(origin: str) -> str:
    return origin.strip().title()


def _format_alcohol(ocr_abv: Any) -> Optional[str]:
    if ocr_abv is None:
        return None
    try:
        abv = float(ocr_abv)
    except (TypeError, ValueError):
        return None
    if abv != abv:  # NaN
        return None
    proof = int(round(abv * 2))
    return f"{abv:g}% Alc./Vol. ({proof} Proof)"


def _format_volume(volume: Any, unit: Any) -> Optional[str]:
    if volume is None or unit is None:
        return None
    try:
        v = float(volume)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    unit_str = str(unit).strip()
    if not unit_str or unit_str.lower() == "nan":
        return None
    v_str = f"{int(v)}" if v.is_integer() else f"{v:g}"
    return f"{v_str} {unit_str}"


def _producer_address(applicant: Optional[str], state: Optional[str]) -> Optional[str]:
    if not applicant:
        return None
    if state:
        return f"{applicant.strip()}, {state.strip().upper()}"
    return applicant.strip()


def _all_match_field_results(is_import: bool) -> Dict[str, Dict[str, str]]:
    base = {
        "brand_name": {"status": "match", "reason_code": "exact_match"},
        "class_type": {"status": "match", "reason_code": "exact_match"},
        "alcohol_content": {"status": "match", "reason_code": "exact_match"},
        "net_contents": {"status": "match", "reason_code": "exact_match"},
        "producer_name_address": {"status": "match", "reason_code": "exact_match"},
        "government_warning": {"status": "match", "reason_code": "exact_match"},
    }
    if is_import:
        base["country_of_origin"] = {"status": "match", "reason_code": "exact_match"}
    else:
        base["country_of_origin"] = {
            "status": "not_applicable",
            "reason_code": "not_applicable",
        }
    return base


def _expected_tags(is_import: bool) -> List[str]:
    tags = ["real_label", "clean_match"]
    tags.append("import_required" if is_import else "domestic_not_applicable")
    return tags


def build_case(raw: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    ttb_id = str(raw["ttb_id"])
    front = _pick_front(raw.get("images", []))
    if not front:
        return None

    gt = raw.get("ground_truth", {}) or {}
    ocr_ref = raw.get("cola_cloud_ocr_reference", {}) or {}

    brand = gt.get("brand_name")
    class_name = gt.get("class_name")
    applicant = gt.get("applicant_name")
    state = gt.get("address_state")
    origin = gt.get("origin")

    # Minimal data needed to construct an application payload
    if not (brand and class_name and applicant):
        return None

    alcohol = _format_alcohol(ocr_ref.get("ocr_abv"))
    volume = _format_volume(ocr_ref.get("ocr_volume"), ocr_ref.get("ocr_volume_unit"))
    if not (alcohol and volume):
        # Skip cases without COLA-Cloud OCR reference for ABV/volume.
        return None

    is_import = _derive_is_import(origin)
    country = _title_country(origin) if (is_import and origin) else None

    fixture_rel = f"ttb_eval/{front['path']}"

    application = {
        "beverage_type": "distilled_spirits",
        "brand_name": brand.strip(),
        "class_type": class_name.strip(),
        "alcohol_content": alcohol,
        "net_contents": volume,
        "producer_name_address": _producer_address(applicant, state),
        "is_import": is_import,
        "country_of_origin": country,
        "government_warning": CANONICAL_WARNING,
    }

    return {
        "inputs": {
            "case_id": f"ttb_{ttb_id}",
            "label_image_path": fixture_rel,
            "application": application,
        },
        "outputs": {
            "overall_verdict": "match",
            "recommended_action": "accept",
            "field_results": _all_match_field_results(is_import),
            "expected_tags": _expected_tags(is_import),
        },
        "metadata": {
            "source": "ttb_cola_2017",
            "ttb_id": ttb_id,
            "origin": origin,
            "front_image": front["path"],
            "front_image_alt": front.get("type"),
            "abv_source": "cola_cloud_ocr_reference",
            "volume_source": "cola_cloud_ocr_reference",
            "warning_source": "canonical_ttb_text",
        },
    }



def _tag_field_sources(
    application: Mapping[str, Any],
    corrections: Mapping[str, Any],
) -> Dict[str, str]:
    return {
        field: ("hand_labeled" if field in corrections else "csv")
        for field in application
    }


def build_cases_with_corrections(
    source: Path = SOURCE_PATH,
    corrections: Path = CORRECTIONS_PATH,
    output: Path = OUTPUT_PATH,
) -> Dict[str, Any]:
    corrections_by_id = _load_corrections(corrections)

    with source.open("r", encoding="utf-8") as fh:
        raw_cases = [json.loads(line) for line in fh if line.strip()]

    built: List[Dict[str, Any]] = []
    skipped: List[str] = []
    corrected = 0

    for raw in raw_cases:
        case = build_case(raw)
        if case is None:
            skipped.append(str(raw.get("ttb_id")))
            continue

        cid = case["inputs"]["case_id"]
        row = corrections_by_id.get(cid)
        if row:
            for field, value in row["corrections"].items():
                if field in CORRECTIBLE_FIELDS and value:
                    case["inputs"]["application"][field] = value
            corrected += 1
            case["metadata"]["field_sources"] = _tag_field_sources(
                case["inputs"]["application"], row["corrections"]
            )
            case["metadata"]["labeled_by"] = row.get("labeled_by")
            case["metadata"]["labeled_at"] = row.get("labeled_at")
        else:
            case["metadata"]["field_sources"] = _tag_field_sources(
                case["inputs"]["application"], {}
            )

        built.append(case)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for case in built:
            fh.write(json.dumps(case) + "\n")

    return {
        "source": str(source),
        "corrections": str(corrections),
        "output": str(output),
        "built": len(built),
        "corrected_cases": corrected,
        "skipped": skipped,
    }


if __name__ == "__main__":
    summary = build_cases_with_corrections()
    print(json.dumps(summary, indent=2))
