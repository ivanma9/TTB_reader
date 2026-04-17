# Real-label Category B — front+back image contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the `government_warning` gap (39/43 `unreadable` because the warning lives on the back label) by extending the verifier contract to accept an optional `back_image_path`, wiring it through the real-label eval, and confirming a measurable delta.

**Architecture:** Minimum-surface contract change. Add an optional `back_image_path` parameter at every boundary (`adapter.py`, `service.py`, eval harness, `cases.jsonl`). When present, OCR the back image and **concatenate** its lines after the front lines — no sorting, no tagging. `partition_lines` already scans sequentially for the `"GOVERNMENT WARNING"` prefix, so placing back lines after front naturally routes the warning into `warning_anchor`/`warning_body` without touching partitioning or matchers. Field matchers remain image-agnostic; they just see a longer line list when back is provided.

**Tech Stack:** Python 3.11, pytest, existing PaddleOCR pipeline via `alc_label_verifier.ocr.extract_lines`, real-label eval at `evals/real_labels/analyze.py`.

**Baseline (at HEAD after Category A merges):** `government_warning` 0/43 match, 39/43 `unreadable`. `net_contents` may also improve as a side-effect if volume is printed on the back panel.

**Ship criteria:**
- `government_warning` match count ≥ 25/43 (from 0/43 baseline).
- No field regresses from its baseline (`match` monotonically non-decreasing per field).
- All tests green, including synthetic golden-set (which calls with `back_path=None`).

**Explicitly out of scope:**
- Reviewer-workbench UI two-upload (M4 UI work — separate pass).
- Side-aware matchers (matchers stay image-agnostic this pass).
- Golden-set regeneration with back fixtures (they remain single-image).
- `producer_name_address` / `class_type` CSV-truth relabeling (Category C).

---

## Task 1: Extend `verify_label` to accept optional back image

**Files:**
- Modify: `alc_label_verifier/service.py:47` (`verify_label` signature + OCR step)
- Modify: `alc_label_verifier/adapter.py:10-14` (`target` reads optional key)
- Test: `tests/test_contract.py` or a new `tests/test_back_image.py`

### Step 1.1: Write a failing test — single-image call still works

`tests/test_back_image.py` (new file):

```python
from alc_label_verifier.service import verify_label


def _app(**overrides):
    base = {
        "beverage_type": "distilled_spirits",
        "brand_name": "Test",
        "class_type": "Whiskey",
        "alcohol_content": "40% Alc./Vol.",
        "net_contents": "750 milliliters",
        "producer_name_address": "Test Co., KY",
        "is_import": False,
        "government_warning": "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS.",
    }
    base.update(overrides)
    return base


def test_verify_label_accepts_optional_back_path_none(monkeypatch):
    # back_path=None must behave exactly like a single-image call.
    from alc_label_verifier import service as svc

    captured_paths = []

    def fake_extract_lines(path):
        captured_paths.append(path)
        return []  # empty lines → returns all-unreadable result

    monkeypatch.setattr(svc, "extract_lines", fake_extract_lines)
    result = verify_label("front.png", _app(), back_path=None)
    assert captured_paths == ["front.png"], "back_path=None should OCR only front"
    assert "field_results" in result
```

### Step 1.2: Run the test — confirm FAIL

Run: `source .venv/bin/activate && python -m pytest tests/test_back_image.py -v`
Expected: FAIL with `TypeError: verify_label() got an unexpected keyword argument 'back_path'`.

### Step 1.3: Implement the signature change

In `alc_label_verifier/service.py`, change the signature and OCR block:

```python
def verify_label(
    image_path: str,
    application: Dict[str, Any],
    back_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full verification pipeline and return a result dict.

    When back_path is provided, OCR is run on both images and the line lists
    are concatenated (front first, back second) before partitioning. The
    ordering matters: partition_lines searches sequentially for the
    GOVERNMENT WARNING anchor, so back lines placed after front lines route
    the warning (if it lives on the back) into warning_anchor/warning_body
    without any partitioning changes.
    """
    t0 = time.monotonic()
    try:
        lines = extract_lines(image_path)
    except UnreadableImageError:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        result = _all_unreadable_result()
        result["processing_ms"] = elapsed_ms
        return result

    if back_path:
        try:
            back_lines = extract_lines(back_path)
            lines = lines + back_lines
        except UnreadableImageError:
            pass  # Back image unreadable is non-fatal; proceed with front only.

    # ... rest unchanged
```

Add `Optional` to the imports if it isn't already there.

### Step 1.4: Run the test — confirm PASS

Run: `python -m pytest tests/test_back_image.py -v`
Expected: PASS.

### Step 1.5: Write a failing test — back image feeds lines into partition

Append to `tests/test_back_image.py`:

```python
def test_verify_label_back_image_lines_reach_warning_matcher(monkeypatch):
    from alc_label_verifier import service as svc
    from alc_label_verifier.ocr import OcrLine

    front_lines = [
        OcrLine(text="TEST BOURBON", confidence=0.99, bbox=[], y_center=0, x_center=0),
        OcrLine(text="Whiskey", confidence=0.99, bbox=[], y_center=1, x_center=0),
        OcrLine(text="40% Alc./Vol.", confidence=0.99, bbox=[], y_center=2, x_center=0),
        OcrLine(text="750 mL", confidence=0.99, bbox=[], y_center=3, x_center=0),
        OcrLine(text="Test Co., KY", confidence=0.99, bbox=[], y_center=4, x_center=0),
    ]
    back_lines = [
        OcrLine(
            text="GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS.",
            confidence=0.95,
            bbox=[],
            y_center=0,
            x_center=0,
        ),
    ]

    path_to_lines = {"f.png": front_lines, "b.png": back_lines}
    monkeypatch.setattr(svc, "extract_lines", lambda p: path_to_lines[p])

    result = verify_label("f.png", _app(), back_path="b.png")
    warning_result = result["field_results"]["government_warning"]
    assert warning_result["status"] == "match", (
        f"Expected warning match when back provides anchor line, got {warning_result}"
    )
```

### Step 1.6: Run both tests — confirm the new one passes

Run: `python -m pytest tests/test_back_image.py -v`
Expected: both PASS. If the warning match test fails, trace through `partition_lines` — the `GOVERNMENT WARNING` prefix should be at position 5 (after 5 front lines) and partition cleanly. If it fails for a reason other than the contract (e.g. warning body parsing), fix in-place; the test validates the integration path, not the warning matcher itself.

### Step 1.7: Extend `adapter.target` to pass `back_image_path` through

In `alc_label_verifier/adapter.py`:

```python
def target(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter hook consumed by evals/adapter.py via ALC_EVAL_TARGET."""
    image_path: str = inputs["label_image_path"]
    back_path = inputs.get("back_image_path")
    application: Dict[str, Any] = inputs["application"]
    return verify_label(image_path, application, back_path=back_path)
```

### Step 1.8: Run the full test suite

Run: `python -m pytest`
Expected: all tests pass. If any synthetic golden-set test regresses, the contract change broke backward-compat — investigate before proceeding.

### Step 1.9: Commit

```bash
git add alc_label_verifier/service.py alc_label_verifier/adapter.py tests/test_back_image.py
git commit -m "$(cat <<'EOF'
feat: verify_label accepts optional back_image_path [ship]

Extends the contract so callers can pass a second image for the bottle's
back panel. When provided, OCR runs on both and the line lists are
concatenated (front first, then back). Partitioning finds the
"GOVERNMENT WARNING" prefix wherever it lives — no matcher changes
needed. back_path=None preserves exact existing behavior so the 28
synthetic golden-set cases continue to pass unchanged.

No eval delta yet — Task 2 wires the real-label eval to actually pass
back_image_path through.
EOF
)"
```

---

## Task 2: Wire back image through the real-label eval

**Files:**
- Modify: `evals/real_labels/adapter.py` (add `_pick_back`, emit `back_image_path` in case inputs)
- Regenerate: `evals/real_labels/cases.jsonl`
- Verify: `evals/real_labels/analyze.py` already forwards all `inputs` keys via `dict(case["inputs"])` — no change needed, but confirm.

### Step 2.1: Inspect the raw source format

Run: `head -1 ttb_eval/cases.jsonl | python -c "import sys, json; d=json.loads(sys.stdin.read()); print([i.get('panel') for i in d.get('images',[])])"`
Expected: see `['front', 'back']` or similar. Confirms back-panel availability.

If `ttb_eval/cases.jsonl` doesn't exist or has no back panels, STOP and ask — the scraper may need to be rerun. Check `scripts/ttb_eval_builder.py` for where `images` is populated.

### Step 2.2: Write a failing test for the adapter

Append to `tests/test_field_parsing.py` or create `tests/test_real_labels_adapter.py`:

```python
from evals.real_labels.adapter import build_case


def test_build_case_emits_back_image_path_when_back_panel_present():
    raw = {
        "ttb_id": "18011001000033",
        "images": [
            {"panel": "front", "path": "images/18011001000033_0_front.jpg"},
            {"panel": "back", "path": "images/18011001000033_0_back.jpg"},
        ],
        "ground_truth": {
            "brand_name": "Ron Cartavio",
            "class_name": "rum",
            "applicant_name": "Cartavio Rum Co.",
            "address_state": None,
            "origin": "Peru",
        },
        "cola_cloud_ocr_reference": {
            "ocr_abv": 40.0,
            "ocr_volume": 750,
            "ocr_volume_unit": "milliliters",
        },
    }
    case = build_case(raw)
    assert case is not None
    assert case["inputs"]["back_image_path"] == "ttb_eval/images/18011001000033_0_back.jpg"


def test_build_case_omits_back_image_path_when_no_back_panel():
    raw = {
        "ttb_id": "18011001000033",
        "images": [
            {"panel": "front", "path": "images/18011001000033_0_front.jpg"},
        ],
        "ground_truth": {
            "brand_name": "X",
            "class_name": "y",
            "applicant_name": "Z",
            "address_state": None,
            "origin": None,
        },
        "cola_cloud_ocr_reference": {
            "ocr_abv": 40.0,
            "ocr_volume": 750,
            "ocr_volume_unit": "milliliters",
        },
    }
    case = build_case(raw)
    assert case is not None
    assert "back_image_path" not in case["inputs"]
```

### Step 2.3: Run — confirm FAIL

Run: `python -m pytest tests/test_real_labels_adapter.py -v` (or the file you appended to)
Expected: FAIL (no `back_image_path` in adapter output).

### Step 2.4: Implement `_pick_back` and extend `build_case`

In `evals/real_labels/adapter.py`:

```python
def _pick_back(images: List[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    for img in images:
        if img.get("panel") == "back":
            return img
    return None
```

In `build_case`, after the existing `fixture_rel = f"ttb_eval/{front['path']}"` line:

```python
    back = _pick_back(raw.get("images", []))
    back_fixture_rel = f"ttb_eval/{back['path']}" if back else None
```

And in the returned dict, change the `inputs` block to conditionally include `back_image_path`:

```python
    inputs_block = {
        "case_id": f"ttb_{ttb_id}",
        "label_image_path": fixture_rel,
        "application": application,
    }
    if back_fixture_rel:
        inputs_block["back_image_path"] = back_fixture_rel

    return {
        "inputs": inputs_block,
        "outputs": {
            # ... unchanged
        },
        "metadata": {
            # ... unchanged, plus:
            "back_image": back["path"] if back else None,
        },
    }
```

### Step 2.5: Run the adapter tests — confirm PASS

Run: `python -m pytest tests/test_real_labels_adapter.py -v`
Expected: both PASS.

### Step 2.6: Regenerate `cases.jsonl`

Run: `python -m evals.real_labels.adapter`
Expected: prints a summary dict; `evals/real_labels/cases.jsonl` is rewritten with `back_image_path` on cases that have a back panel.

Verify visually: `grep -c back_image_path evals/real_labels/cases.jsonl` — should match the count of cases with a back panel in the source.

### Step 2.7: Verify `analyze.py` forwards the new key

Read `evals/real_labels/analyze.py::_run_verifier`:

```python
def _run_verifier(case):
    inputs = dict(case["inputs"])
    inputs["label_image_path"] = resolve_fixture_path(inputs["label_image_path"], ROOT_DIR)
    return verify_target(inputs)
```

It dumps all `inputs` through to `verify_target`. The `back_image_path` key, if present, flows through to `adapter.target` which reads `inputs.get("back_image_path")`. But the path needs `resolve_fixture_path` applied too. Add:

```python
def _run_verifier(case):
    inputs = dict(case["inputs"])
    inputs["label_image_path"] = resolve_fixture_path(inputs["label_image_path"], ROOT_DIR)
    if "back_image_path" in inputs:
        inputs["back_image_path"] = resolve_fixture_path(inputs["back_image_path"], ROOT_DIR)
    return verify_target(inputs)
```

### Step 2.8: Run the full eval — record deltas

Run: `python -m evals.real_labels.analyze`
Then:

```python
python -c "
import csv
rows = list(csv.DictReader(open('docs/real-label-gaps.csv')))
for field in ['brand_name','class_type','alcohol_content','net_contents','producer_name_address','country_of_origin','government_warning']:
    c = {k:0 for k in ['match','mismatch','needs_review','not_applicable']}
    for r in rows: c[r[f'{field}_actual']] = c.get(r[f'{field}_actual'],0)+1
    print(f'{field:25s} {c}')
"
```

Record the counts. Primary target: `government_warning` match ≥ 25/43. Watch `net_contents` (may improve as side-effect). Watch every other field to confirm no regression.

### Step 2.9: Commit

```bash
git add evals/real_labels/adapter.py evals/real_labels/cases.jsonl evals/real_labels/analyze.py tests/test_real_labels_adapter.py docs/real-label-gaps.csv docs/real-label-gaps-latest.md
git commit -m "$(cat <<'EOF'
feat: real-label eval feeds back images through the verifier [ship]

TTB source already includes back-panel images (just filtered out of the
earlier adapter). Now the adapter emits back_image_path and the analyzer
resolves+forwards it, so government_warning finally gets the lines it
needs to match.

Real-label eval deltas:
- government_warning match: 0/43 → <FILL>/43
- net_contents match:       <PRE>/43 → <POST>/43
- <any other moves>
EOF
)"
```

---

## Task 3: Iteration loop

**Trigger:** after Task 2 commits, inspect the new numbers. If plateau is below expectations, investigate before committing more code.

### Step 3.1: Categorize remaining warning failures

For each case where `government_warning_actual != "match"`, run the OCR dump (see Tools appendix) on the back image and classify:
- **OCR quality** — warning text is present but confidence is low or tokens are broken. → consider image preprocessing in `ocr.py::preprocess` for the back image (e.g. contrast stretch) or a back-image-specific confidence gate.
- **Missing panel** — no back image in source. → document, not fixable here.
- **Warning elsewhere** — warning on the front bottle-neck, side panel, etc. → out of scope; note.

### Step 3.2: Check for regressions on other fields

Compare the pre-Task-2 `docs/real-label-gaps.csv` (from git history) with the post-Task-2 version. Any field where `match` count dropped is a regression caused by back-panel lines polluting a matcher's input pool. Most-likely culprit: `brand_name` picks a back-panel line, `match_country_of_origin` finds a back-panel phrase that outscores the front one.

For each regression:
- Write a regression test capturing the bad case.
- Decide: tighten the matcher OR add source-awareness (would bump matchers out of image-agnostic — if needed, flag as a scope-expansion question before coding).

### Step 3.3: Commit fixes individually with `[ship]` if the eval moves, bare commit if internal-only

Per-iteration: one focused change, one regression test, one eval re-run. Stop when two consecutive iterations produce no new matches and no regressions.

### Step 3.4: Update curated `docs/real-label-gaps.md`

After the plateau, edit `docs/real-label-gaps.md` (the curated doc, NOT the `-latest.md` auto-generated one) with:
- New headline numbers per field.
- List of Category C cases surviving (back-panel missing, relabel needed, etc.).
- Any residual gaps with the root-cause classification.

Commit as `docs: update real-label gaps after Category B` (no `[ship]`).

---

## Tools appendix

**OCR dump for a back image by case_id:**

```bash
source .venv/bin/activate && python -c "
from pathlib import Path
import json
from alc_label_verifier.ocr import extract_lines
from evals.golden_set.evaluators import resolve_fixture_path
from evals.golden_set.schema import ROOT_DIR
cases = [json.loads(l) for l in open('evals/real_labels/cases.jsonl')]
target_id = 'ttb_18289001000377'  # <-- change me
for c in cases:
    if c['inputs']['case_id'] == target_id:
        back = c['inputs'].get('back_image_path')
        if not back:
            print(f'{target_id}: no back image'); break
        img = resolve_fixture_path(back, ROOT_DIR)
        print(f'{target_id} back:')
        for l in extract_lines(img):
            print(f'  {l.confidence:.2f} {l.text!r}')
        break
" 2>&1 | grep -v ppocr | grep -v warn | grep -v ccache
```

**Per-field eval delta vs prior commit:**

```bash
source .venv/bin/activate && git show HEAD^:docs/real-label-gaps.csv > /tmp/before.csv && python -c "
import csv
def counts(path):
    rows = list(csv.DictReader(open(path)))
    out = {}
    for f in ['brand_name','class_type','alcohol_content','net_contents','producer_name_address','country_of_origin','government_warning']:
        c = {k:0 for k in ['match','mismatch','needs_review','not_applicable']}
        for r in rows: c[r[f'{f}_actual']] = c.get(r[f'{f}_actual'],0)+1
        out[f] = c
    return out
b, a = counts('/tmp/before.csv'), counts('docs/real-label-gaps.csv')
for f in b:
    if b[f] != a[f]: print(f'{f:25s} before={b[f]} after={a[f]}')
"
```

## Success rubric

- `government_warning` match ≥ 25/43 (from 0/43).
- No field regresses.
- All tests green, synthetic golden-set untouched.
- Curated `docs/real-label-gaps.md` updated with new numbers and surviving Category C cases.
- Commits tagged `[ship]` per per-task templates.
