"""Interactive CLI to hand-label real-label cases with on-label class and
producer values, overriding the structurally-wrong CSV truth.

Usage:
    python -m scripts.label_real_cases --limit 20

Writes to evals/real_labels/corrections.jsonl (one JSON object per case).
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

CORRECTIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "real_labels"
    / "corrections.jsonl"
)

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "real_labels" / "cases.jsonl"


def load_corrections(path: Path) -> Dict[str, Dict[str, Any]]:
    """Return {case_id: row_dict}. Empty / missing file returns {}."""
    if not path.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        out[row["case_id"]] = row
    return out


def save_correction(
    path: Path,
    *,
    case_id: str,
    labeled_by: str,
    corrections: Mapping[str, Any],
) -> None:
    """Append or replace the row for case_id. File stays JSONL."""
    existing = load_corrections(path)
    existing[case_id] = {
        "case_id": case_id,
        "labeled_by": labeled_by,
        "labeled_at": dt.date.today().isoformat(),
        "corrections": dict(corrections),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in existing.values():
            fh.write(json.dumps(row) + "\n")


def _open_image(img: Path) -> None:
    """Open the image in the system default viewer (macOS `open`).

    Non-blocking: returns immediately; the reviewer inspects the image while
    we print OCR lines. Safe to call multiple times per case.
    """
    try:
        subprocess.run(["open", str(img)], check=False)
    except FileNotFoundError:
        print(f"    (could not open {img} — `open` unavailable on this platform)")


def _dump_ocr(label: str, image_rel: Optional[str]) -> None:
    from evals.golden_set.evaluators import resolve_fixture_path
    from evals.golden_set.schema import ROOT_DIR
    from alc_label_verifier.ocr import extract_lines

    if not image_rel:
        print(f"  [{label}] (no image)")
        return
    img = Path(resolve_fixture_path(image_rel, ROOT_DIR))
    print(f"  [{label}] ({img.name})")
    _open_image(img)
    try:
        for line in extract_lines(img):
            print(f"    {line.confidence:.2f}  {line.text}")
    except Exception as e:
        print(f"    OCR failed: {e}")


def _prompt(current: Optional[str], field: str) -> Optional[str]:
    print(f"\n  Current CSV truth for {field}: {current!r}")
    print(f"  Enter on-label {field} (blank to keep CSV truth, '!skip' to skip this case):")
    entry = input("    > ").strip()
    if entry == "!skip":
        return "__SKIP__"
    return entry or None


def label_cases(limit: int, labeled_by: str) -> None:
    cases = [json.loads(l) for l in CASES_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    cases.sort(key=lambda c: c["inputs"]["case_id"])
    existing = load_corrections(CORRECTIONS_PATH)

    to_do = [c for c in cases[:limit] if c["inputs"]["case_id"] not in existing]
    print(f"{len(to_do)} case(s) remaining to label (limit={limit}; {len(existing)} already labeled).")

    for i, case in enumerate(to_do, 1):
        cid = case["inputs"]["case_id"]
        app = case["inputs"]["application"]
        print(f"\n=== [{i}/{len(to_do)}] {cid} ===")
        print(f"  brand={app.get('brand_name')!r}  is_import={app.get('is_import')}  origin={app.get('country_of_origin')}")
        _dump_ocr("FRONT", case["inputs"].get("label_image_path"))
        _dump_ocr("BACK", case["inputs"].get("back_image_path"))

        corrections: Dict[str, Any] = {}
        for field in ("class_type", "producer_name_address"):
            value = _prompt(app.get(field), field)
            if value == "__SKIP__":
                corrections = {"__SKIPPED__": True}
                break
            if value is not None:
                corrections[field] = value

        if corrections.get("__SKIPPED__"):
            print("  skipped — not writing correction")
            continue

        save_correction(CORRECTIONS_PATH, case_id=cid, labeled_by=labeled_by, corrections=corrections)
        print(f"  saved → {CORRECTIONS_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="Max cases to label this run")
    parser.add_argument(
        "--labeled-by",
        default=getpass.getuser(),
        help="Name recorded in corrections.jsonl; defaults to $USER",
    )
    args = parser.parse_args()
    label_cases(limit=args.limit, labeled_by=args.labeled_by)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
