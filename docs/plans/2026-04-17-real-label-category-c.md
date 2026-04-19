# Real-label Category C — hand-labeled class_type & producer_name_address Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the real-label eval score `class_type` and `producer_name_address` against *what's actually on the label* (fanciful class names, bottler name + address) instead of the structurally wrong CSV defaults (TTB class codes, permit-holder applicant name). Produce a 20-case hand-labeled corrections file, wire it through the eval adapter, re-measure deltas, and surface any residual verifier gaps as follow-up work.

**Architecture:** An image-and-OCR-assisted CLI (`scripts/label_real_cases.py`) walks the first 20 cases by `case_id`, opens each front+back image in the system default viewer (macOS `open`), prints the OCR output as a scaffold, prompts the reviewer to paste on-label values, and appends to `evals/real_labels/corrections.jsonl`. The eval adapter (`evals/real_labels/adapter.py`) merges corrections over CSV-derived fields at `cases.jsonl` build time, tagging each field's source in `metadata`. `analyze.py` partitions per-field counts by `labeled_vs_unlabeled` so the delta is measurable on the 20 labeled cases without noise from the 23 unlabeled ones.

**Execution:** Run directly on `main` (Categories A and B already merged). No dedicated worktree.

**Tech Stack:** Python 3.11, existing PaddleOCR pipeline via `alc_label_verifier.ocr.extract_lines`, existing real-label eval harness. No new dependencies.

**Baseline (at Category B HEAD):** `class_type` 1/43 match. `producer_name_address` 0/43 match. Root cause is CSV truth, not matcher bugs (unverified).

**Ship criteria:**
- 20 cases hand-labeled, stored in `evals/real_labels/corrections.jsonl` with provenance metadata.
- Adapter merges corrections deterministically; `cases.jsonl` builds clean.
- Real-label eval on the 20 labeled cases: `class_type` match ≥ 15/20 OR a documented list of verifier gaps exposed (tracked as Category A follow-ups, not fixed here).
- Same threshold for `producer_name_address`.
- No regression on any field for the 23 unlabeled cases.
- `docs/real-label-gaps.md` curated doc updated with labeled-subset numbers.

**Explicitly out of scope:**
- Labeling beyond 20 cases.
- Fixing verifier matchers exposed by the hand labels (those become separate Category A issues).
- Correcting fields other than `class_type` and `producer_name_address`.
- Any UI / reviewer-workbench integration.

---

## Task 1: OCR-assisted labeling CLI

**Files:**
- Create: `scripts/label_real_cases.py`
- Create: `evals/real_labels/corrections.jsonl` (empty, committed as a placeholder)
- Test: `tests/test_label_real_cases.py`

### Step 1.1: Decide and document the corrections file format

`evals/real_labels/corrections.jsonl` — one JSON object per line:

```json
{"case_id": "ttb_18011001000033", "labeled_by": "ivan", "labeled_at": "2026-04-17", "corrections": {"class_type": "Rum", "producer_name_address": "Destileria Cartavio S.A., Pueblo Nuevo s/n, La Libertad, Peru"}}
```

- `case_id` is the join key.
- `corrections` only contains fields being overridden. A case with only `class_type` corrected is valid; `producer_name_address` stays on CSV truth.
- Missing `corrections` (empty dict) means "reviewer saw the case and decided no correction is needed".
- Any extra field in `corrections` is accepted but a warning is logged (so if a future pass corrects `brand_name`, the file format already supports it).

Commit an empty `evals/real_labels/corrections.jsonl` — just a file with a trailing newline, no JSON — so downstream paths work on first run.

### Step 1.2: Write a failing test for the corrections file loader

`tests/test_label_real_cases.py`:

```python
import json
from pathlib import Path

from scripts.label_real_cases import load_corrections, save_correction


def test_load_corrections_empty_file_returns_empty_dict(tmp_path):
    p = tmp_path / "corrections.jsonl"
    p.write_text("")
    assert load_corrections(p) == {}


def test_load_corrections_keys_by_case_id(tmp_path):
    p = tmp_path / "corrections.jsonl"
    p.write_text(
        '{"case_id": "ttb_A", "corrections": {"class_type": "Rum"}}\n'
        '{"case_id": "ttb_B", "corrections": {}}\n'
    )
    out = load_corrections(p)
    assert out["ttb_A"]["corrections"]["class_type"] == "Rum"
    assert out["ttb_B"]["corrections"] == {}


def test_save_correction_appends_to_file(tmp_path):
    p = tmp_path / "corrections.jsonl"
    p.write_text("")
    save_correction(
        p,
        case_id="ttb_X",
        labeled_by="tester",
        corrections={"class_type": "Whiskey"},
    )
    lines = p.read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["case_id"] == "ttb_X"
    assert row["corrections"]["class_type"] == "Whiskey"
    assert "labeled_at" in row


def test_save_correction_replaces_existing_entry(tmp_path):
    p = tmp_path / "corrections.jsonl"
    save_correction(p, case_id="ttb_X", labeled_by="a", corrections={"class_type": "X1"})
    save_correction(p, case_id="ttb_X", labeled_by="b", corrections={"class_type": "X2"})
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    assert len(rows) == 1, "second save must replace, not duplicate"
    assert rows[0]["corrections"]["class_type"] == "X2"
```

### Step 1.3: Run the test — confirm FAIL

Run: `source .venv/bin/activate && python -m pytest tests/test_label_real_cases.py -v`
Expected: ImportError on `scripts.label_real_cases`.

### Step 1.4: Implement the file loader/saver

`scripts/__init__.py` — create empty file if missing.

`scripts/label_real_cases.py` (partial; add the interactive CLI in step 1.6):

```python
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
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

CORRECTIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "real_labels"
    / "corrections.jsonl"
)


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
```

### Step 1.5: Run the tests — confirm PASS

Run: `python -m pytest tests/test_label_real_cases.py -v`
Expected: 4 PASS.

### Step 1.6: Build the interactive labeling loop

Append to `scripts/label_real_cases.py`:

```python
import subprocess

from evals.golden_set.evaluators import resolve_fixture_path
from evals.golden_set.schema import ROOT_DIR
from alc_label_verifier.ocr import extract_lines

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "real_labels" / "cases.jsonl"


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
    if not image_rel:
        print(f"  [{label}] (no image)")
        return
    img = resolve_fixture_path(image_rel, ROOT_DIR)
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
```

### Step 1.7: Smoke-test the CLI in dry mode

Run: `python -m scripts.label_real_cases --limit 1`
Expected: CLI prints OCR for the first case, prompts for input. Hit `!skip` to exit without writing.

If the CLI crashes on OCR (e.g. PaddleOCR init), fix before Task 2.

### Step 1.8: Commit

```bash
git add scripts/__init__.py scripts/label_real_cases.py tests/test_label_real_cases.py evals/real_labels/corrections.jsonl
git commit -m "$(cat <<'EOF'
feat: CLI for OCR-assisted real-label corrections

Labels class_type and producer_name_address on real TTB cases by showing
the reviewer front+back OCR output and writing to corrections.jsonl.
Empty corrections.jsonl committed as a placeholder — labels land in Task 2.
EOF
)"
```

---

## Task 2: Hand-label 20 cases

**Files:**
- Modify: `evals/real_labels/corrections.jsonl` (add 20 rows)

### Step 2.1: Run the labeling CLI

From the repo root:

```
python -m scripts.label_real_cases --limit 20
```

For each case:
1. The CLI opens the front and back images in the system default viewer. **Look at the images first** — they are the source of truth. Use the OCR dump as a scaffold for fast copy-paste, not as authority.
2. Identify the on-label **class text** — the fanciful class name printed in large type (e.g. "Kentucky Straight Bourbon Whiskey", "Cachaça", "Single Malt Scotch Whisky"). If the label only shows "WHISKEY" or the class is implied, use the narrowest accurate on-label phrase.
3. Identify the **bottler / producer name + address** on the label — usually printed near the bottom or on the back panel as "Bottled by [Name], [City], [State/Country]" or "Produced and Bottled by...". Paste the full string as it appears on the image (case-preserved, OCR-corrected when OCR misreads).
4. Leave blank if the on-label value is genuinely identical to the CSV truth (rare but possible).
5. Use `!skip` if the image is illegible or missing — the case stays unlabeled and is excluded from scoring.

### Step 2.2: Sanity-check the saved file

```
python -c "
import json
rows = [json.loads(l) for l in open('evals/real_labels/corrections.jsonl').read().splitlines() if l.strip()]
print(f'{len(rows)} rows')
for r in rows:
    k = ', '.join(sorted(r['corrections']))
    print(f'  {r[\"case_id\"]}: [{k}]  by={r[\"labeled_by\"]}')
"
```

Expected: ~20 rows (some may be `!skip`-ped). Each row has at least one correction field.

### Step 2.3: Commit

```bash
git add evals/real_labels/corrections.jsonl
git commit -m "$(cat <<'EOF'
chore: hand-labeled 20 real-label cases for class_type and producer

First pass of on-label corrections — CSV "APPLICANT_NAME" and TTB class
codes replaced with what's actually printed on the label. Enables real
scoring of class_type and producer_name_address in the next task.
EOF
)"
```

(No `[ship]` — this is data, not shipped code.)

---

## Task 3: Merge corrections in the eval adapter + re-run

**Files:**
- Modify: `evals/real_labels/adapter.py` (merge corrections at build time)
- Modify: `evals/real_labels/analyze.py` (partition counts by labeled vs unlabeled)
- Regenerate: `evals/real_labels/cases.jsonl`
- Test: `tests/test_real_labels_adapter.py` (new tests for corrections merge)

### Step 3.1: Write failing tests for the corrections merge

Append to `tests/test_real_labels_adapter.py` (or create it):

```python
import json
from pathlib import Path

from evals.real_labels.adapter import build_cases_with_corrections


def _raw(tmp_path):
    src = tmp_path / "source.jsonl"
    src.write_text(json.dumps({
        "ttb_id": "18011001000033",
        "images": [{"panel": "front", "path": "images/f.jpg"}],
        "ground_truth": {
            "brand_name": "Cartavio",
            "class_name": "other rum gold fb",
            "applicant_name": "Import Co LLC",
            "address_state": None,
            "origin": "Peru",
        },
        "cola_cloud_ocr_reference": {
            "ocr_abv": 40.0,
            "ocr_volume": 750,
            "ocr_volume_unit": "milliliters",
        },
    }) + "\n")
    return src


def test_build_applies_corrections_and_tags_source(tmp_path):
    src = _raw(tmp_path)
    corr = tmp_path / "corrections.jsonl"
    corr.write_text(json.dumps({
        "case_id": "ttb_18011001000033",
        "labeled_by": "tester",
        "labeled_at": "2026-04-17",
        "corrections": {
            "class_type": "Rum",
            "producer_name_address": "Destileria Cartavio S.A., La Libertad, Peru",
        },
    }) + "\n")
    out = tmp_path / "cases.jsonl"

    summary = build_cases_with_corrections(source=src, corrections=corr, output=out)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    case = rows[0]
    assert case["inputs"]["application"]["class_type"] == "Rum"
    assert "Cartavio" in case["inputs"]["application"]["producer_name_address"]
    assert case["metadata"]["field_sources"]["class_type"] == "hand_labeled"
    assert case["metadata"]["field_sources"]["brand_name"] == "csv"
    assert summary["corrected_cases"] == 1


def test_build_leaves_uncorrected_cases_on_csv_truth(tmp_path):
    src = _raw(tmp_path)
    corr = tmp_path / "corrections.jsonl"
    corr.write_text("")
    out = tmp_path / "cases.jsonl"

    build_cases_with_corrections(source=src, corrections=corr, output=out)
    row = json.loads(out.read_text().splitlines()[0])
    assert row["inputs"]["application"]["class_type"] == "other rum gold fb"
    assert row["metadata"]["field_sources"]["class_type"] == "csv"
```

### Step 3.2: Run — confirm FAIL

Run: `python -m pytest tests/test_real_labels_adapter.py -k corrections -v`
Expected: `ImportError: cannot import name 'build_cases_with_corrections'`.

### Step 3.3: Implement `build_cases_with_corrections`

In `evals/real_labels/adapter.py`, add (keep the existing `build_cases` working for back-compat):

```python
CORRECTIONS_PATH = ROOT / "evals" / "real_labels" / "corrections.jsonl"
CORRECTIBLE_FIELDS = ("class_type", "producer_name_address")


def _load_corrections(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        out[row["case_id"]] = row
    return out


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
        case = build_case(raw)  # re-use the existing CSV-only builder
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
```

Update `if __name__ == "__main__":` block at the bottom to call the new function:

```python
if __name__ == "__main__":
    summary = build_cases_with_corrections()
    print(json.dumps(summary, indent=2))
```

### Step 3.4: Run the tests — confirm PASS

Run: `python -m pytest tests/test_real_labels_adapter.py -v`
Expected: all existing adapter tests + the two new corrections tests PASS.

### Step 3.5: Regenerate `cases.jsonl`

Run: `python -m evals.real_labels.adapter`
Expected: summary prints `"corrected_cases": ~20`. Verify:

```
python -c "
import json
rows = [json.loads(l) for l in open('evals/real_labels/cases.jsonl').read().splitlines()]
labeled = [r for r in rows if r['metadata'].get('labeled_by')]
print(f'{len(labeled)}/{len(rows)} cases have hand labels')
"
```

### Step 3.6: Extend `analyze.py` to partition counts by label source

In `evals/real_labels/analyze.py`, add a second per-field table restricted to hand-labeled cases. In the loop, track `case["metadata"].get("labeled_by")` and accumulate into a separate `labeled_field_status_counts` Counter. Render a second section in the output markdown:

```python
# After the existing per-field table:
lines.append("\n## Per-field status — hand-labeled subset only\n")
labeled_rows = [r for r in rows if r.get("labeled_by")]
lines.append(f"Cases in subset: {len(labeled_rows)}")
lines.append("| Field | match | mismatch | needs_review | not_applicable |")
lines.append("|-------|-------|----------|--------------|----------------|")
for field in FIELD_NAMES:
    c = labeled_field_status_counts[field]
    lines.append(
        f"| {field} | {c.get('match',0)} | {c.get('mismatch',0)} | "
        f"{c.get('needs_review',0)} | {c.get('not_applicable',0)} |"
    )
```

Accumulation detail: when writing the CSV row, also emit a `labeled_by` column so the post-run python snippet can partition easily. (Alternative: parse `field_sources` from metadata at analyze time — fine either way.)

### Step 3.7: Run the eval — capture deltas on the labeled subset

```
python -m evals.real_labels.analyze
```

Then:

```
python -c "
import csv
rows = list(csv.DictReader(open('docs/real-label-gaps.csv')))
labeled = [r for r in rows if r.get('labeled_by')]
print(f'Hand-labeled subset: {len(labeled)} cases')
for field in ['class_type', 'producer_name_address']:
    c = {k:0 for k in ['match','mismatch','needs_review','not_applicable']}
    for r in labeled: c[r[f'{field}_actual']] = c.get(r[f'{field}_actual'],0)+1
    print(f'  {field:25s} {c}')
"
```

Record the counts. Targets on the 20-case labeled subset:
- `class_type` ≥ 15/20 match
- `producer_name_address` ≥ 15/20 match

### Step 3.8: Check for regressions on the 23 unlabeled cases

Compare pre/post match counts for ALL fields on the unlabeled subset. A correctly-implemented merge should produce ZERO change on unlabeled cases. Any regression means the `build_case` path changed behavior unintentionally — investigate.

### Step 3.9: Commit

```bash
git add evals/real_labels/adapter.py evals/real_labels/analyze.py evals/real_labels/cases.jsonl tests/test_real_labels_adapter.py docs/real-label-gaps.csv docs/real-label-gaps-latest.md
git commit -m "$(cat <<'EOF'
feat: real-label eval merges hand-labeled corrections [ship]

Adapter now applies evals/real_labels/corrections.jsonl over CSV-derived
fields at build time, tagging each field's source in metadata.
analyze.py renders a second per-field table restricted to the hand-labeled
subset so class_type and producer_name_address can finally be scored
against what's actually on the label.

Real-label eval deltas (20-case labeled subset):
- class_type match:             1/43 → <FILL>/20 (subset)
- producer_name_address match:  0/43 → <FILL>/20 (subset)
- Full 43-case set: no regressions on other fields.
EOF
)"
```

---

## Task 4: Iteration — classify residual failures

**Trigger:** after Task 3 commits, inspect failures on the labeled subset.

### Step 4.1: For each labeled case where `class_type` or `producer_name_address` is NOT `match`, classify

Categorize each failure:
- **A** — matcher bug (the on-label value IS in the OCR output, verifier just didn't pick it up). File as a Category-A follow-up issue; do NOT fix in this plan.
- **B** — OCR quality (the on-label value is garbled in OCR). File as a back-label / preprocessing follow-up; do NOT fix in this plan.
- **C** — label ambiguity (the reviewer's hand-label doesn't match any plausible on-label string; e.g. long address with multiple candidate lines). Re-run the CLI on those specific cases and refine the label.

### Step 4.2: Refine labels in-place where appropriate

For Category C, re-run:

```
python -m scripts.label_real_cases --limit 20
```

The CLI skips already-labeled cases by default. For refinement, temporarily edit `corrections.jsonl` to remove the problem row, then re-label. (Or add a `--force <case_id>` flag if this becomes common — not required this pass.)

Re-run the eval. Stop iterating when two consecutive rounds produce no new matches on the labeled subset.

### Step 4.3: Document Category A and B follow-ups

Append to `docs/real-label-gaps.md` (curated doc, not `-latest.md`) a section `### Category C residuals`:

- For each Category A case: case_id, field, expected (hand-labeled), actual (observed), hypothesis for matcher fix. These become candidates for a future Category A plan.
- For each Category B case: case_id, field, note on OCR failure.

Commit as `docs: real-label gaps — Category C labeled-subset results` (no `[ship]`).

---

## Tools appendix

**Show the full OCR + case info for a specific case:**

```python
source .venv/bin/activate && python -c "
from pathlib import Path
import json
from alc_label_verifier.ocr import extract_lines
from evals.golden_set.evaluators import resolve_fixture_path
from evals.golden_set.schema import ROOT_DIR
cases = [json.loads(l) for l in open('evals/real_labels/cases.jsonl')]
target = 'ttb_18011001000033'  # <-- change me
c = next(c for c in cases if c['inputs']['case_id']==target)
print('expected:', c['inputs']['application'])
print('meta:', c['metadata'])
for panel_key, label in [('label_image_path','FRONT'),('back_image_path','BACK')]:
    p = c['inputs'].get(panel_key)
    if not p: continue
    img = resolve_fixture_path(p, ROOT_DIR)
    print(f'--- {label} ---')
    for l in extract_lines(img):
        print(f'  {l.confidence:.2f} {l.text!r}')
" 2>&1 | grep -v ppocr | grep -v warn | grep -v ccache
```

**Post-run summary restricted to labeled subset:**

```python
source .venv/bin/activate && python -c "
import csv
rows = list(csv.DictReader(open('docs/real-label-gaps.csv')))
labeled = [r for r in rows if r.get('labeled_by')]
print(f'labeled subset: {len(labeled)} / {len(rows)} total')
for field in ['class_type','producer_name_address']:
    for subset, label in [(labeled, 'labeled'), (rows, 'all')]:
        c = {k:0 for k in ['match','mismatch','needs_review','not_applicable']}
        for r in subset: c[r[f'{field}_actual']] = c.get(r[f'{field}_actual'],0)+1
        print(f'  {field:25s} [{label:7s}]  {c}')
"
```

## Success rubric

- 20 rows in `evals/real_labels/corrections.jsonl`, each with `class_type` and `producer_name_address` on-label values.
- Adapter tests green; no regression on the 23 unlabeled cases.
- `class_type` match ≥ 15/20 on labeled subset OR documented matcher-bug list for the gap.
- `producer_name_address` match ≥ 15/20 on labeled subset OR documented matcher-bug list for the gap.
- `docs/real-label-gaps.md` curated doc updated with labeled-subset numbers and Category A/B follow-up entries.
- `[ship]` commit on Task 3.
