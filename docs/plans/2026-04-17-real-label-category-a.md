# Real-label Category A — verifier improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the three verifier-side gaps surfaced by the TTB real-label eval (`net_contents`, `brand_name`, `country_of_origin` residual) so a broader share of the labeled 43-case set produces actionable match/mismatch verdicts instead of `unreadable`/`missing_required`.

**Architecture:** Each task follows a **measure → fix → re-measure → iterate until plateau** loop. The real-label eval (`python -m evals.real_labels.analyze`) is the source of truth for deltas; synthetic golden-set regressions (`tests/test_integration.py`) are the guard against overfitting. No fix ships until: (a) new unit tests exercise the fix directly, (b) whole test suite passes, (c) real-label delta is non-negative on every other field, (d) real-label delta on the target field has plateaued.

**Tech Stack:** Python 3.11, rapidfuzz, re, pytest. All changes in `alc_label_verifier/matching.py` and `tests/test_field_parsing.py`. Eval harness in `evals/real_labels/analyze.py`.

**Baseline (at HEAD 9b03f75), real-label eval on 43 cases:**

| Field | match | mismatch | needs_review |
|---|---:|---:|---:|
| net_contents | 0 | 0 | 43 |
| brand_name | 7 | 18 | 18 |
| country_of_origin (25 imports) | 1 | 7 | 17 |

**Ship criteria (working targets, revise if plateau falls short):**
- `net_contents`: ≥ 20/43 match
- `brand_name`: ≥ 20/43 match
- `country_of_origin`: ≥ 3/25 match, OR document that remaining gaps require back-label (Category B)

---

## Task 1: `net_contents` — fix expected-value parser + OCR-typo tolerance

**Root cause (confirmed):** `parse_net_contents("750 milliliters")` returns `None` because the unit regex accepts only `mL|ML|ml|L|oz|fl oz`, not the English word `"milliliters"`. Every real case expects `"750 milliliters"`, so `expected_parsed is None`, the matcher falls to a whole-line fuzzy fallback, and fails.

**Secondary cause:** OCR frequently reads `"L"` as digit `"1"` on labels (observed in `ttb_18289001000377`: `'(80%PROOF) CONT.750m1'`). The regex rejects `m1` as a unit.

**Files:**
- Modify: `alc_label_verifier/matching.py:46-49` (the `_NET_RE` regex) and `:63-77` (`parse_net_contents`)
- Test: `tests/test_field_parsing.py` (append net-contents-alias tests at end of file)

### Step 1.1: Write failing tests for the expected-value aliases

Append to `tests/test_field_parsing.py`:

```python
from alc_label_verifier.matching import parse_net_contents


def test_parse_net_contents_accepts_milliliters_spelled_out():
    assert parse_net_contents("750 milliliters") == (750.0, "ml")


def test_parse_net_contents_accepts_liter_spelled_out():
    assert parse_net_contents("1 liter") == (1000.0, "ml")
    assert parse_net_contents("1.75 liters") == (1750.0, "ml")


def test_parse_net_contents_accepts_fluid_ounces_spelled_out():
    assert parse_net_contents("25.4 fluid ounces") == (25.4, "oz")
```

### Step 1.2: Run the tests, confirm they fail

Run: `source .venv/bin/activate && python -m pytest tests/test_field_parsing.py -k net_contents_accepts -v`
Expected: 3 FAIL (`parse_net_contents` returns `None` for the spelled-out units).

### Step 1.3: Broaden the unit regex in `matching.py`

Replace lines 46–49:

```python
_NET_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(fl\.?\s*oz|fluid\s+ounces?|ounces?|oz|"
    r"milliliters?|mL|ML|ml|"
    r"liters?|L)\b",
    re.IGNORECASE,
)
```

And update `parse_net_contents` (lines 63–77) to normalize the new aliases:

```python
def parse_net_contents(text: str) -> Optional[Tuple[float, str]]:
    """Return (quantity_ml_or_oz, unit_string) or None if not parseable.

    Normalises to two canonical units: 'ml' (with L → mL conversion) or 'oz'.
    Accepts both symbol forms (mL, L, oz) and English words (milliliters,
    liters, fluid ounces) — the CSV ground truth in our eval sets uses the
    spelled-out forms while real labels use the symbol forms.
    """
    m = _NET_RE.search(text)
    if not m:
        return None
    qty = float(m.group(1))
    unit_raw = m.group(2).lower().replace(" ", "").replace(".", "")
    if unit_raw in ("l", "liter", "liters"):
        return (qty * 1000, "ml")
    if unit_raw.startswith("fl") or unit_raw in ("oz", "ounce", "ounces", "fluidounce", "fluidounces"):
        return (qty, "oz")
    return (qty, "ml")
```

### Step 1.4: Run the 3 new tests — confirm PASS

Run: `python -m pytest tests/test_field_parsing.py -k net_contents_accepts -v`
Expected: 3 PASS.

### Step 1.5: Write failing test for OCR-typo "m1" → "ml"

Append:

```python
def test_parse_net_contents_tolerates_l_read_as_digit_one():
    # OCR frequently reads 'L' as '1' on label typography.
    assert parse_net_contents("CONT.750m1") == (750.0, "ml")
    assert parse_net_contents("750 M1") == (750.0, "ml")
```

### Step 1.6: Run test, confirm FAIL

Run: `python -m pytest tests/test_field_parsing.py -k tolerates_l_read -v`
Expected: FAIL.

### Step 1.7: Extend `_NET_RE` to accept `m1`/`M1` as an OCR-typo alias for `ml`

```python
_NET_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(fl\.?\s*oz|fluid\s+ounces?|ounces?|oz|"
    r"milliliters?|mL|ML|ml|m1|M1|"
    r"liters?|L)\b",
    re.IGNORECASE,
)
```

And in `parse_net_contents`, extend the `ml` branch:

```python
    if unit_raw in ("m1", "ml", "milliliter", "milliliters"):
        return (qty, "ml")
    # ... (rest of function)
```

(Adjust final `return (qty, "ml")` fallback to stay correct.)

### Step 1.8: Run tests — confirm all net_contents tests PASS

Run: `python -m pytest tests/test_field_parsing.py -k net_contents -v`
Expected: ALL PASS (existing + 4 new).

### Step 1.9: Run full suite — no regressions

Run: `python -m pytest`
Expected: 139+ pass (132 pre-Task-3 baseline + 3 country-anchor regressions from 9b03f75 + 4 new net_contents).

### Step 1.10: Run real-label eval, capture delta

Run: `python -m evals.real_labels.analyze`
Then: `python -c "import csv; rows=list(csv.DictReader(open('docs/real-label-gaps.csv'))); print({k: sum(1 for r in rows if r['net_contents_actual']==k) for k in ['match','mismatch','needs_review','not_applicable']})"`

Record the counts. Target: ≥ 20/43 match.

### Step 1.11: Iteration loop

If net_contents match < 20/43:
- Use `evals/real_labels/analyze.py` CSV to find cases still in `needs_review` / `mismatch`.
- Run OCR on the failing case's image (see pattern in the "Tools" appendix below) and inspect the raw lines.
- Identify the next OCR-typo pattern or unit-alias gap.
- Write a failing test for that specific pattern.
- Extend the regex minimally; avoid broadening so far that unit detection false-fires on ABV lines like `'Alc.40%'`.
- Re-run eval. Repeat until match count stops rising (two consecutive iterations with no new match).

### Step 1.12: Commit

```bash
git add alc_label_verifier/matching.py tests/test_field_parsing.py docs/real-label-gaps.csv docs/real-label-gaps-latest.md
git commit -m "$(cat <<'EOF'
fix: net_contents parses spelled-out units and OCR-typo variants [ship]

CSV ground truth says "750 milliliters", labels say "750 mL" or OCR-garbled
"CONT.750m1" (L read as digit 1). Old regex accepted only the symbol forms,
so parse_net_contents returned None on the expected string and every case
fell through to needs_review. Broadened the unit alternatives and added
m1/M1 as an OCR alias.

Real-label eval net_contents match: 0/43 → <FILL IN AFTER RUN>/43.
EOF
)"
```

Also update `docs/real-label-gaps.md` (curated) with the new numbers if you want — NOT via `analyze.py` which writes to `-latest.md`.

---

## Task 2: `brand_name` — fuzzy-contains against expected

**Root cause:** `match_brand_name` takes lines 0–2 of OCR output, concatenates prefixes, and picks the one with highest `token_sort_ratio` against expected. When OCR's top-3 lines are `['CACHACA', 'E', 'PRODUCT OF BRAZIL']` and expected is `'Bucco'`, token_sort_ratio is low on every combination and the matcher returns whichever combo is least-bad — producing `wrong_value=CACHACA`. The real brand line ("Bucco") is often OCR'd further down (position 4+) as a smaller font.

**Fix approach:** Widen the candidate pool to the top N lines (tune N; start with 6), AND score candidates by fuzzy-contains (`partial_ratio`) against expected, not by full `token_sort_ratio`. `partial_ratio("BUCCO 1925", "Bucco") == 100` even though the line has extra tokens.

**Files:**
- Modify: `alc_label_verifier/matching.py:185-212` (`match_brand_name`)
- Test: `tests/test_field_parsing.py`

### Step 2.1: Write failing test — brand on line 4, class word on line 1

```python
def test_match_brand_name_finds_brand_below_class_word():
    lines = [
        OcrLine(text="CACHACA", confidence=0.99, bbox=[], y_center=0, x_center=0),
        OcrLine(text="PRODUCT OF BRAZIL", confidence=0.99, bbox=[], y_center=1, x_center=0),
        OcrLine(text="BUCCO", confidence=0.95, bbox=[], y_center=2, x_center=0),
        OcrLine(text="DESDE 1925", confidence=0.99, bbox=[], y_center=3, x_center=0),
    ]
    result = match_brand_name(lines, "Bucco")
    assert result.status == "match"


def test_match_brand_name_finds_brand_inside_noisy_line():
    # "OREGON" is a prominent region word; "Old Tom" is the brand embedded in
    # a longer line.
    lines = [
        OcrLine(text="OREGON", confidence=0.99, bbox=[], y_center=0, x_center=0),
        OcrLine(text="Old Tom Gin", confidence=0.95, bbox=[], y_center=1, x_center=0),
    ]
    result = match_brand_name(lines, "Old Tom")
    assert result.status == "match"
```

### Step 2.2: Run — confirm FAIL

Run: `python -m pytest tests/test_field_parsing.py -k brand_name_finds -v`
Expected: 2 FAIL.

### Step 2.3: Rewrite `match_brand_name`

Replace lines 185–212 with:

```python
def match_brand_name(lines: List[OcrLine], expected: str) -> FieldResult:
    """Brand: widen the candidate window and prefer partial_ratio against expected.

    Real labels frequently show the class word ("CACHACA") or region
    ("OREGON") in the largest font, with the brand rendered smaller further
    down. A partial_ratio score lets us pick the line that *contains* the
    expected brand even when it's embedded in a noisier string (e.g.
    'BUCCO 1925') or appears below a louder header.
    """
    if not lines:
        return FieldResult(status="needs_review", reason_code="unreadable")

    norm_exp = normalize_text(expected)
    pool = lines[: min(6, len(lines))]

    # Score each line by fuzzy-contains against expected; tiebreaker on confidence.
    scored = [
        (line, fuzz.partial_ratio(normalize_text(line.text), norm_exp))
        for line in pool
    ]
    scored.sort(key=lambda ls: (ls[1], ls[0].confidence), reverse=True)

    best_line, best_score = scored[0]

    # If no line scores well on partial_ratio, fall back to prior behavior
    # (concatenation of lines[0..n] scored by token_sort_ratio) — this
    # preserves the multi-line-brand case (e.g. "THE / ORIGINAL").
    if best_score < 80:
        candidates = lines[: min(3, len(lines))]
        combined = [
            (" ".join(l.text for l in candidates[:n]),
             min(l.confidence for l in candidates[:n]))
            for n in range(1, len(candidates) + 1)
        ]
        best_text, best_conf = max(
            combined,
            key=lambda tc: fuzz.token_sort_ratio(normalize_text(tc[0]), norm_exp),
        )
        if best_conf < STANDARD_CONFIDENCE_THRESHOLD:
            return FieldResult(status="needs_review", reason_code="unreadable")
        return _compare_text(best_text, expected, best_conf, use_fuzzy=True)

    if best_line.confidence < STANDARD_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable")

    return _compare_text(best_line.text, expected, best_line.confidence, use_fuzzy=True)
```

### Step 2.4: Run new tests — PASS

Run: `python -m pytest tests/test_field_parsing.py -k brand_name_finds -v`
Expected: 2 PASS.

### Step 2.5: Run ALL brand tests + full suite

Run: `python -m pytest tests/test_field_parsing.py -k brand -v` then `python -m pytest`
Expected: all pass. If any pre-existing brand test regresses, DO NOT weaken the test — adjust the new scoring (e.g. raise/lower the 80 threshold, widen pool beyond 6) until both old and new tests pass.

### Step 2.6: Run integration suite specifically

Run: `python -m pytest tests/test_integration.py -v`
Expected: all 6 golden-set cases still pass. This is the anti-overfitting guard — if the new brand picker breaks a synthetic case, it's wrong.

### Step 2.7: Run real-label eval, record delta

Run: `python -m evals.real_labels.analyze`
Then summarize brand_name actual-status counts (same pattern as Step 1.10).
Target: ≥ 20/43 match.

### Step 2.8: Iteration loop

Same loop as Task 1:
- Inspect still-failing cases' top 6 OCR lines.
- Identify the pattern (brand tokenized into multiple lines? expected brand has a diacritic OCR mis-read?).
- Add a minimal regression test for the pattern.
- Tighten the scoring (adjust pool size, thresholds, or add a diacritic-normalization step).
- Re-run. Stop when two consecutive iterations yield no new matches.

### Step 2.9: Commit

```bash
git add alc_label_verifier/matching.py tests/test_field_parsing.py docs/real-label-gaps.csv docs/real-label-gaps-latest.md
git commit -m "$(cat <<'EOF'
fix: brand_name picks expected-matching line over loud class/region words [ship]

Old picker scored lines[0..2] by token_sort_ratio to expected — fine when
the brand is the biggest header, broken when "CACHACA"/"OREGON" tower over
a smaller brand line. Switched to partial_ratio scoring over a 6-line
window so the brand is found even when embedded in noise or positioned
below a louder region word.

Real-label eval brand_name match: 7/43 → <FILL>/43.
EOF
)"
```

---

## Task 3: `country_of_origin` residual 7 `missing_required`

**Unknown root cause until investigated.** Likely candidates:
- Anchor phrase split across two OCR lines ("PRODUCT OF" then "BRAZIL" on the next line).
- Anchor on a low-confidence line that gets dropped by the `STANDARD_CONFIDENCE_THRESHOLD` gate.
- Country on the back label (Category B — defer and document).

**Files (investigation only until root cause is known):**
- Read: `docs/real-label-gaps.csv` to list the 7 `missing_required` cases.
- Read: sample OCR output for each (use the pattern in the Tools appendix).

### Step 3.1: Enumerate the 7 failing cases

Run:

```python
python -c "
import csv
for r in csv.DictReader(open('docs/real-label-gaps.csv')):
    if r['country_of_origin_actual']=='mismatch' and r['country_of_origin_reason']=='missing_required':
        print(r['case_id'], '| is_import=', r['is_import'])
"
```

### Step 3.2: For each case, dump OCR lines and classify the failure mode

For each case_id, run the OCR dump script (see Tools appendix) and examine:
- Is there any line containing a known anchor phrase, even low-confidence?
- Is the country name present anywhere in the OCR output?
- Is the anchor split across two adjacent lines?

Categorize each case into one of:
- **A** — anchor split across lines (fixable here)
- **B** — anchor below confidence threshold on a readable label (fixable)
- **C** — no anchor and no country name in OCR at all (likely back-label, defer)

### Step 3.3: If any Category A cases exist, add multi-line anchor join

Write a failing test first, e.g.:

```python
def test_match_country_of_origin_split_across_two_lines():
    lines = [
        OcrLine(text="PRODUCT OF", confidence=0.95, bbox=[], y_center=0, x_center=0),
        OcrLine(text="BRAZIL", confidence=0.95, bbox=[], y_center=1, x_center=0),
    ]
    result = match_country_of_origin(lines, "Brazil", is_import=True)
    assert result.status == "match"
```

Then extend `match_country_of_origin` to: when an anchor line has no extractable value after it, join with the next line in y-order and retry extraction. Implement behind the existing candidate-iteration loop so both current and joined forms are considered.

### Step 3.4: If any Category B cases exist, relax confidence gate with fallback

Consider a lower confidence threshold *only* for country_of_origin (e.g. 0.70 instead of STANDARD_CONFIDENCE_THRESHOLD), returning `needs_review` instead of `unreadable` when a low-confidence value is found — which is still more actionable than `missing_required`. Write a test. Implement. Justify in a code comment.

### Step 3.5: Category C cases — document, don't fix here

Add a paragraph to `docs/real-label-gaps.md` listing each Category C case_id with a note: "country appears on back label only — defer to Category B front+back contract extension".

### Step 3.6: Re-run real-label eval, record delta

Same pattern as prior tasks. Target: ≥ 3/25 match (or documented "N cases are Category C, N' are Category A/B and fixed").

### Step 3.7: Iteration loop

Same loop: inspect remaining failures, tighten, re-measure, stop at plateau.

### Step 3.8: Commit

```bash
git add alc_label_verifier/matching.py tests/test_field_parsing.py docs/real-label-gaps.csv docs/real-label-gaps-latest.md docs/real-label-gaps.md
git commit -m "$(cat <<'EOF'
fix: country_of_origin recovers from split-line anchors and low-conf labels [ship]

Of the 7 remaining missing_required cases after the anchor-broadening work,
N were Category A (anchor split across two OCR lines), N were Category B
(low-confidence readable anchor), N were Category C (back label — deferred).
Added a split-line join in match_country_of_origin and a country-specific
confidence fallback; documented Category C cases in real-label-gaps.md.

Real-label eval country_of_origin match (25 imports): 1/25 → <FILL>/25.
EOF
)"
```

---

## Tools appendix

**OCR dump for a single case:**

```python
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
        img = resolve_fixture_path(c['inputs']['label_image_path'], ROOT_DIR)
        print('expected:', c['inputs']['application'])
        print('---')
        for l in extract_lines(img):
            print(f'{l.confidence:.2f} {l.text!r}')
        break
" 2>&1 | grep -v ppocr | grep -v warn | grep -v ccache
```

**Per-field eval-count summary:**

```python
source .venv/bin/activate && python -c "
import csv
rows = list(csv.DictReader(open('docs/real-label-gaps.csv')))
for field in ['brand_name','class_type','alcohol_content','net_contents','producer_name_address','country_of_origin','government_warning']:
    c = {k:0 for k in ['match','mismatch','needs_review','not_applicable']}
    for r in rows: c[r[f'{field}_actual']] = c.get(r[f'{field}_actual'],0)+1
    print(f'{field:25s} {c}')
"
```

---

## Out of scope (explicitly deferred)

- **Front+back label input contract** (Category B). Unlocks `government_warning` (39/43 unreadable) and some `net_contents` residuals. Requires adapter contract change, caller migration, and eval-set re-feeding. Track separately in an M4 addendum.
- **`class_type` and `producer_name_address` hand-relabeling** (Category C). CSV ground truth is structurally wrong for these two fields — `APPLICANT_NAME` ≠ on-label bottler, `CLASS_NAME` ≠ on-label fanciful name. Requires manual labeling, not code. Track separately.

## Success rubric

At completion of all three tasks:
- Real-label match totals improve on at least 2 of 3 target fields.
- No field regresses from its baseline (`match` count monotonically non-decreasing).
- Golden-set integration tests still 100% green (`test_integration.py`).
- `docs/real-label-gaps.md` curated doc updated with the new numbers and residual gaps.
- Commits tagged `[ship]` per per-task commit template.
