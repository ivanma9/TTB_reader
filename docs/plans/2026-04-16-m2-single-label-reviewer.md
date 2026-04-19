# M2 Single-Label Reviewer Workbench — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a FastAPI + Jinja + HTMX web app that lets a reviewer upload one distilled-spirits label image, enter expected application data, and get a verdict plus field-by-field results in ≤5 seconds.

**Architecture:** FastAPI serves a single-page Jinja template and a `POST /verify` endpoint that writes the uploaded image to a temp file, calls the existing `alc_label_verifier.service.verify_label`, deletes the temp file, and returns an HTMX-swappable HTML fragment. The existing eval harness and golden-set contract are unchanged.

**Tech Stack:** Python 3.11, FastAPI 0.111+, uvicorn[standard], Jinja2, python-multipart, HTMX 1.9 (loaded from CDN), existing `alc_label_verifier` package.

**M1 status:** Complete — `python3 evals/run_golden_set.py` reports 100% on all gates. Do not modify the eval harness or the golden-set contract.

---

## Task 1: Enrich FieldResult with observed_value

**Files:**
- Modify: `alc_label_verifier/models.py`
- Test: `tests/test_normalization.py` (add one regression assertion)

**Step 1: Confirm FieldResult only has status and reason_code**

```bash
grep -n "class FieldResult" alc_label_verifier/models.py
```

Expected: lines 19-22 show `status` and `reason_code` only.

**Step 2: Write a test asserting the new field exists and defaults to None**

Add to `tests/test_normalization.py` (top of file is fine):

```python
from alc_label_verifier.models import FieldResult

def test_field_result_observed_value_defaults_to_none():
    fr = FieldResult(status="match", reason_code="exact_match")
    assert fr.observed_value is None
```

**Step 3: Run — confirm failure**

```bash
pytest tests/test_normalization.py::test_field_result_observed_value_defaults_to_none -v
```

Expected: `AttributeError` or `TypeError`.

**Step 4: Add observed_value to FieldResult**

In `alc_label_verifier/models.py`, update the import block at the top:

```python
from typing import Dict, List, Optional
```

Then update FieldResult:

```python
@dataclass
class FieldResult:
    status: str        # match | mismatch | needs_review | not_applicable
    reason_code: str
    observed_value: Optional[str] = None
```

**Step 5: Run tests — confirm pass + eval gates still pass**

```bash
pytest tests/test_normalization.py::test_field_result_observed_value_defaults_to_none -v
python3 evals/run_golden_set.py
```

Expected: test PASS; all eval gates `true`.

**Step 6: Commit**

```bash
git add alc_label_verifier/models.py tests/test_normalization.py
git commit -m "feat: add observed_value to FieldResult for UI display"
```

---

## Task 2: Populate observed_value in key matchers

**Files:**
- Modify: `alc_label_verifier/matching.py`

**Step 1: Write a unit test confirming observed_value is set on mismatch**

Add to `tests/test_normalization.py`:

```python
from alc_label_verifier.matching import match_brand_name
from alc_label_verifier.models import OcrLine

def test_match_brand_name_sets_observed_value_on_mismatch():
    lines = [OcrLine(text="WRONG BRAND", confidence=0.95, bbox=[], y_center=0, x_center=0)]
    result = match_brand_name(lines, "CORRECT BRAND")
    assert result.status == "mismatch"
    assert result.observed_value == "WRONG BRAND"

def test_match_brand_name_sets_observed_value_on_match():
    lines = [OcrLine(text="MY BRAND", confidence=0.97, bbox=[], y_center=0, x_center=0)]
    result = match_brand_name(lines, "MY BRAND")
    assert result.status == "match"
    assert result.observed_value == "MY BRAND"
```

**Step 2: Run — confirm failure**

```bash
pytest tests/test_normalization.py::test_match_brand_name_sets_observed_value_on_mismatch tests/test_normalization.py::test_match_brand_name_sets_observed_value_on_match -v
```

Expected: FAIL (observed_value is None).

**Step 3: Update matchers to populate observed_value**

In `alc_label_verifier/matching.py`, make these targeted changes:

**match_brand_name** — add `result.observed_value` after the final `_compare_text` call, and populate it on the early-exit too:

```python
def match_brand_name(lines: List[OcrLine], expected: str) -> FieldResult:
    if not lines:
        return FieldResult(status="needs_review", reason_code="unreadable")

    norm_exp = normalize_text(expected)
    candidates = lines[:min(3, len(lines))]

    best_line = max(
        candidates,
        key=lambda l: fuzz.token_sort_ratio(normalize_text(l.text), norm_exp),
    )

    if best_line.confidence < STANDARD_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable",
                           observed_value=best_line.text)

    result = _compare_text(best_line.text, expected, best_line.confidence, use_fuzzy=True)
    result.observed_value = best_line.text
    return result
```

**match_class_type** — set observed_value on the returned result:

```python
def match_class_type(class_lines: List[OcrLine], expected: str) -> FieldResult:
    if not class_lines:
        return FieldResult(status="needs_review", reason_code="unreadable")

    confidence = min(l.confidence for l in class_lines)
    ocr_text = " ".join(l.text for l in class_lines)

    if confidence < STANDARD_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable",
                           observed_value=ocr_text)

    result = _compare_text(ocr_text, expected, confidence, use_fuzzy=True)
    result.observed_value = ocr_text
    return result
```

**match_alcohol_content** — add `observed_value` to each of the three non-None returns:

```python
    if match_line is not None:
        reason = "exact_match" if match_line.text.strip() == expected.strip() else "normalized_match"
        return FieldResult(status="match", reason_code=reason,
                           observed_value=match_line.text)

    if mismatch_line is not None:
        if mismatch_line.confidence >= STANDARD_CONFIDENCE_THRESHOLD:
            return FieldResult(status="mismatch", reason_code="wrong_value",
                               observed_value=mismatch_line.text)
        return FieldResult(status="needs_review", reason_code="unreadable",
                           observed_value=mismatch_line.text)
```

**match_net_contents** — same pattern as alcohol_content.

**match_producer_name_address** — add observed_value to the three explicit returns (after the `not producer_lines` check, after confidence check, and on the final two returns):

```python
def match_producer_name_address(lower_lines: List[OcrLine], expected: str) -> FieldResult:
    producer_lines = [
        l for l in lower_lines
        if not l.text.lower().startswith("country of origin")
    ]

    if not producer_lines:
        return FieldResult(status="needs_review", reason_code="unreadable")

    confidence = min(l.confidence for l in producer_lines)
    ocr_text = " ".join(l.text for l in producer_lines)

    if confidence < STANDARD_CONFIDENCE_THRESHOLD:
        return FieldResult(status="needs_review", reason_code="unreadable",
                           observed_value=ocr_text)

    norm_ocr = normalize_text(ocr_text)
    norm_exp = normalize_text(expected)

    if norm_ocr == norm_exp:
        reason = "exact_match" if ocr_text.strip() == expected.strip() else "normalized_match"
        return FieldResult(status="match", reason_code=reason, observed_value=ocr_text)

    if fuzz.token_set_ratio(norm_ocr, norm_exp) >= 92:
        return FieldResult(status="match", reason_code="normalized_match",
                           observed_value=ocr_text)

    return FieldResult(status="mismatch", reason_code="wrong_value",
                       observed_value=ocr_text)
```

**match_country_of_origin** — add observed_value on the match/mismatch returns where `after` is extracted:

After `after = raw[sep + len("country of origin"):].lstrip(": ").strip()`, update:

```python
    if norm_after == norm_expected:
        reason = "exact_match" if after.strip() == (expected or "").strip() else "normalized_match"
        return FieldResult(status="match", reason_code=reason, observed_value=after)

    return FieldResult(status="mismatch", reason_code="wrong_value", observed_value=after)
```

**match_government_warning** — add observed_value for the prefix-error and body-mismatch paths. After `ocr_body` is assembled:

```python
    if not raw_prefix_line.startswith(GOVERNMENT_WARNING_PREFIX):
        return FieldResult(status="mismatch", reason_code="warning_prefix_error",
                           observed_value=raw_prefix_line)
    # ...
    if norm_ocr_body == norm_exp_body:
        return FieldResult(status="match", reason_code="exact_match",
                           observed_value=ocr_body[:200])

    return FieldResult(status="mismatch", reason_code="warning_text_mismatch",
                       observed_value=ocr_body[:200])
```

**Step 4: Run all tests and eval**

```bash
pytest tests/ -v
python3 evals/run_golden_set.py
```

Expected: all existing tests pass; all eval gates `true`.

**Step 5: Commit**

```bash
git add alc_label_verifier/matching.py tests/test_normalization.py
git commit -m "feat: populate observed_value in field matchers for UI display"
```

---

## Task 3: Add processing_ms to service

**Files:**
- Modify: `alc_label_verifier/service.py`
- Test: `tests/test_integration.py` (real integration test against a fixture)

**Step 1: Write a failing integration test**

Add to `tests/test_integration.py`:

```python
@pytest.mark.integration
def test_verify_label_returns_processing_ms():
    from alc_label_verifier.service import verify_label
    result = verify_label(
        "evals/golden_set/fixtures/gs_001.png",
        {
            "beverage_type": "distilled_spirits",
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "producer_name_address": "Old Tom Distillery, Louisville, KY",
            "is_import": False,
            "country_of_origin": None,
            "government_warning": (
                "GOVERNMENT WARNING: According to the Surgeon General, women should not "
                "drink alcoholic beverages during pregnancy because of the risk of birth "
                "defects. Consumption of alcoholic beverages impairs your ability to drive "
                "a car or operate machinery, and may cause health problems."
            ),
        },
    )
    assert "processing_ms" in result, "processing_ms key missing from result"
    assert isinstance(result["processing_ms"], int)
    assert result["processing_ms"] >= 0
```

**Step 2: Run — confirm failure**

```bash
pytest tests/test_integration.py::test_verify_label_returns_processing_ms -v -m integration
```

Expected: `KeyError: 'processing_ms'` or `AssertionError`.

**Step 3: Update service.py — timing, serialise observed_value, and fix _all_unreadable_result**

Three changes in `alc_label_verifier/service.py`:

**a) Update `_all_unreadable_result` to include `observed_value: None` per field** (consistent shape with the normal path):

```python
def _all_unreadable_result() -> Dict[str, Any]:
    field_results = {
        name: {"status": "needs_review", "reason_code": "unreadable", "observed_value": None}
        for name in FIELD_NAMES
    }
    return {
        "overall_verdict": "needs_review",
        "recommended_action": "request_better_image",
        "field_results": field_results,
    }
```

**b) Add `import time` at the top and wrap `verify_label` with timing:**

```python
import time

def verify_label(image_path: str, application: Dict[str, Any]) -> Dict[str, Any]:
    t_start = time.monotonic()

    lines = extract_lines(image_path)

    if is_globally_unreadable(lines):
        elapsed = int((time.monotonic() - t_start) * 1000)
        result = _all_unreadable_result()
        result["processing_ms"] = elapsed
        return result

    # ... existing pipeline (no other changes) ...

    if unreadable_count >= 4:
        elapsed = int((time.monotonic() - t_start) * 1000)
        result = _all_unreadable_result()
        result["processing_ms"] = elapsed
        return result

    verdict, action = _derive_verdict(field_results)
    elapsed = int((time.monotonic() - t_start) * 1000)
    return {
        "overall_verdict": verdict,
        "recommended_action": action,
        "field_results": {
            name: {"status": fr.status, "reason_code": fr.reason_code,
                   "observed_value": fr.observed_value}
            for name, fr in field_results.items()
        },
        "processing_ms": elapsed,
    }
```

**Step 4: Run all tests + eval**

```bash
pytest tests/ -v -m "not integration"
pytest tests/test_integration.py -v -m integration
python3 evals/run_golden_set.py
```

Expected: all pass; eval gates all `true`; `test_verify_label_returns_processing_ms` PASS.

**Step 5: Commit**

```bash
git add alc_label_verifier/service.py tests/test_integration.py
git commit -m "feat: add processing_ms timing and consistent field shape to verify_label"
```

---

## Task 4: Add web dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `Dockerfile`

**Step 1: Add `[web]` extras to pyproject.toml**

In `pyproject.toml`, add after the existing `[project.optional-dependencies]` block:

```toml
web = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.9",
]
```

**Step 2: Install**

```bash
pip install -e ".[web,dev]"
```

**Step 3: Verify fastapi imports**

```bash
python3 -c "import fastapi; print(fastapi.__version__)"
```

Expected: version string like `0.111.x`.

**Step 4: Update Dockerfile to install web extras**

In `Dockerfile`, change the line:

```dockerfile
RUN pip install --no-cache-dir ".[dev]"
```

to:

```dockerfile
RUN pip install --no-cache-dir ".[web,dev]"
```

**Step 5: Commit**

```bash
git add pyproject.toml Dockerfile
git commit -m "chore: add fastapi/uvicorn/jinja2 web dependencies"
```

---

## Task 5: FastAPI app skeleton with /healthz

**Files:**
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `tests/test_web.py`

**Step 1: Write a failing test for /healthz**

Create `tests/test_web.py`:

```python
"""Web endpoint integration tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_returns_200():
    r = client.get("/healthz")
    assert r.status_code == 200


def test_healthz_returns_ok():
    r = client.get("/healthz")
    assert r.json() == {"status": "ok"}
```

**Step 2: Run — confirm failure**

```bash
pytest tests/test_web.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`.

**Step 3: Create app package skeleton**

Create `app/__init__.py` (empty):

```python
```

Create `app/main.py`:

```python
"""FastAPI web app for the single-label reviewer workbench."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Alcohol Label Verifier")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})
```

**Step 4: Run — confirm pass**

```bash
pytest tests/test_web.py -v
```

Expected: both tests PASS.

**Step 5: Commit**

```bash
git add app/__init__.py app/main.py tests/test_web.py
git commit -m "feat: fastapi app skeleton with /healthz endpoint"
```

---

## Task 6: GET / — serve the index template

**Files:**
- Create: `app/templates/index.html` (minimal scaffold first)
- Modify: `app/main.py`
- Modify: `tests/test_web.py`

**Step 1: Write a failing test for GET /**

Add to `tests/test_web.py`:

```python
def test_index_returns_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_index_contains_form():
    r = client.get("/")
    assert b"Run Verification" in r.content
    assert b"brand_name" in r.content
```

**Step 2: Run — confirm failure**

```bash
pytest tests/test_web.py::test_index_returns_html tests/test_web.py::test_index_contains_form -v
```

Expected: 404 or attribute error.

**Step 3: Add template directory and GET / route**

Create `app/templates/` directory. Create `app/templates/index.html` — the full reviewer form (see Task 10 for the final version; for now use a minimal scaffold):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Alcohol Label Verifier</title>
</head>
<body>
  <form enctype="multipart/form-data" method="post" action="/verify">
    <input type="file" name="image" required>
    <input type="text" name="brand_name" id="brand_name">
    <button type="submit">Run Verification</button>
  </form>
</body>
</html>
```

Update `app/main.py` to mount templates:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Alcohol Label Verifier")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})
```

**Step 4: Run — confirm pass**

```bash
pytest tests/test_web.py -v
```

Expected: all 4 tests PASS.

**Step 5: Commit**

```bash
git add app/main.py app/templates/index.html tests/test_web.py
git commit -m "feat: GET / serves index template with reviewer form scaffold"
```

---

## Task 7: POST /verify — verification endpoint

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_web.py`

**Step 1: Write a failing test for POST /verify**

The test uses `gs_001.png` (domestic match) and the corresponding application data from `cases.jsonl`. The test client sends multipart form data.

Add to `tests/test_web.py`:

```python
from pathlib import Path

FIXTURES = Path("evals/golden_set/fixtures")

GS_001_APPLICATION = {
    "brand_name": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "alcohol_content": "45% Alc./Vol. (90 Proof)",
    "net_contents": "750 mL",
    "producer_name_address": "Old Tom Distillery, Louisville, KY",
    "is_import": "",  # unchecked → empty string
    "country_of_origin": "",
    "government_warning": (
        "GOVERNMENT WARNING: According to the Surgeon General, women should not "
        "drink alcoholic beverages during pregnancy because of the risk of birth "
        "defects. Consumption of alcoholic beverages impairs your ability to drive "
        "a car or operate machinery, and may cause health problems."
    ),
}


def test_verify_returns_200():
    with open(FIXTURES / "gs_001.png", "rb") as f:
        r = client.post(
            "/verify",
            data=GS_001_APPLICATION,
            files={"image": ("gs_001.png", f, "image/png")},
        )
    assert r.status_code == 200


def test_verify_gs001_is_match():
    with open(FIXTURES / "gs_001.png", "rb") as f:
        r = client.post(
            "/verify",
            data=GS_001_APPLICATION,
            files={"image": ("gs_001.png", f, "image/png")},
        )
    assert r.status_code == 200
    # Assert on the recommended action label, which is unique to a clean match
    assert b"Overall Verdict" in r.content
    assert b"Accept" in r.content  # rendered from action_label["accept"]
    assert b"Mismatch" not in r.content


def test_verify_mismatch_shows_mismatch_verdict():
    """Wrong brand name → mismatch result with mismatch banner."""
    wrong_app = {**GS_001_APPLICATION, "brand_name": "COMPLETELY WRONG BRAND XYZ"}
    with open(FIXTURES / "gs_001.png", "rb") as f:
        r = client.post(
            "/verify",
            data=wrong_app,
            files={"image": ("gs_001.png", f, "image/png")},
        )
    assert r.status_code == 200
    assert b"Overall Verdict" in r.content
    assert b"Manual Review" in r.content  # rendered from action_label["manual_review"]


def test_verify_import_missing_country_shows_mismatch():
    """Import flag set but country_of_origin empty → missing_required mismatch."""
    import_app = {**GS_001_APPLICATION, "is_import": "true", "country_of_origin": ""}
    with open(FIXTURES / "gs_001.png", "rb") as f:
        r = client.post(
            "/verify",
            data=import_app,
            files={"image": ("gs_001.png", f, "image/png")},
        )
    assert r.status_code == 200
    assert b"Overall Verdict" in r.content
    # country_of_origin missing_required → mismatch verdict
    assert b"Manual Review" in r.content


def test_verify_unreadable_image_returns_needs_review():
    """A blank/noise image must return needs_review, not a silent failure."""
    import io
    blank_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # malformed PNG
    r = client.post(
        "/verify",
        data=GS_001_APPLICATION,
        files={"image": ("blank.png", blank_image, "image/png")},
    )
    # Must not 500 — should render a graceful result or error fragment
    assert r.status_code == 200
    assert b"Overall Verdict" in r.content or b"error" in r.content.lower()


def test_verify_rejects_oversized_upload():
    """Images over 20 MB are rejected with 413."""
    large_image = b"X" * (21 * 1024 * 1024)
    r = client.post(
        "/verify",
        data=GS_001_APPLICATION,
        files={"image": ("big.png", large_image, "image/png")},
    )
    assert r.status_code == 413
```

**Step 2: Run — confirm failure**

```bash
pytest tests/test_web.py::test_verify_returns_200 tests/test_web.py::test_verify_gs001_is_match -v
```

Expected: 422 or 404 (endpoint doesn't exist yet).

**Step 3a: Create a minimal result.html stub** so the endpoint can render before Task 8 fills it in.

Create `app/templates/result.html` with this stub content:

```html
<div data-verdict="{{ result.overall_verdict }}">
  <p>Overall Verdict</p>
  <p>{{ result.overall_verdict }}</p>
  {% set action_label = {"accept": "Accept", "manual_review": "Manual Review Required", "request_better_image": "Request Better Image"} %}
  <p>{{ action_label.get(result.recommended_action, result.recommended_action) }}</p>
  {% for field_name, fr in result.field_results.items() %}
  <span>{{ fr.status }}</span>
  {% endfor %}
</div>
```

**Step 3b: Add POST /verify to app/main.py**

Add these imports at the top of `app/main.py`:

```python
import os
import tempfile
from pathlib import Path as FilePath

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from alc_label_verifier._constants import FIELD_NAMES
from alc_label_verifier.service import verify_label

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
```

Add the explanation map and the `/verify` endpoint:

```python
_EXPLANATION = {
    "exact_match": "Exact match",
    "normalized_match": "Matched after normalizing case and punctuation",
    "wrong_value": "Value does not match expected",
    "missing_required": "Required field not found on label",
    "not_applicable": "Not required for domestic products",
    "unreadable": "Text could not be read reliably — manual review needed",
    "warning_prefix_error": "Government warning prefix has incorrect formatting",
    "warning_text_mismatch": "Warning text deviates from required statement",
}


@app.post("/verify", response_class=HTMLResponse)
async def verify_endpoint(
    request: Request,
    image: UploadFile = File(...),
    brand_name: str = Form(""),
    class_type: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    producer_name_address: str = Form(""),
    is_import: str = Form(""),
    country_of_origin: str = Form(""),
    government_warning: str = Form(""),
) -> HTMLResponse:
    image_bytes = await image.read()
    if len(image_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 20 MB limit")

    suffix = FilePath(image.filename or "label.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        is_import_flag = is_import.lower() in ("true", "1", "on", "yes", "checked")
        application = {
            "beverage_type": "distilled_spirits",
            "brand_name": brand_name,
            "class_type": class_type,
            "alcohol_content": alcohol_content,
            "net_contents": net_contents,
            "producer_name_address": producer_name_address,
            "is_import": is_import_flag,
            "country_of_origin": country_of_origin or None,
            "government_warning": government_warning,
        }
        raw_result = verify_label(tmp_path, application)
    except Exception as exc:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "result": {
                    "overall_verdict": "needs_review",
                    "recommended_action": "request_better_image",
                    "processing_ms": 0,
                    "error": f"Verification failed: {exc}",
                    "field_results": {
                        name: {
                            "status": "needs_review",
                            "reason_code": "unreadable",
                            "observed_value": None,
                            "explanation": "Text could not be read reliably — manual review needed",
                            "expected_value": "",
                        }
                        for name in FIELD_NAMES
                    },
                },
            },
        )
    finally:
        os.unlink(tmp_path)

    # Enrich field_results for the UI
    enriched = {}
    for field_name in FIELD_NAMES:
        fr = raw_result["field_results"][field_name]
        enriched[field_name] = {
            **fr,
            "explanation": _EXPLANATION.get(fr["reason_code"], fr["reason_code"]),
            "expected_value": application.get(field_name) or "",
        }

    result = {
        "overall_verdict": raw_result["overall_verdict"],
        "recommended_action": raw_result["recommended_action"],
        "processing_ms": raw_result.get("processing_ms", 0),
        "field_results": enriched,
    }

    return templates.TemplateResponse("result.html", {"request": request, "result": result})
```

**Step 4: Run — confirm all new tests pass**

```bash
pytest tests/test_web.py -v
```

Expected: all 11 tests PASS. (The unreadable-image test passes because the exception handler returns a graceful 200; the oversized-upload test passes with 413.)

**Step 5: Also confirm eval gates still pass**

```bash
python3 evals/run_golden_set.py
```

Expected: all gates `true`.

**Step 6: Commit**

```bash
git add app/main.py app/templates/result.html tests/test_web.py
git commit -m "feat: POST /verify with error handling, file-size guard, and result stub"
```

---

## Task 8: Build result.html fragment template

**Files:**
- Modify: `app/templates/result.html` (replace stub from Task 7 with full template)
- Modify: `tests/test_web.py`

**Step 1: Write failing tests for full result content**

The stub from Task 7 doesn't include the "Brand Name" field label or processing time. These tests will fail against the stub.

Add to `tests/test_web.py`:

```python
def test_verify_gs001_shows_field_labels():
    with open(FIXTURES / "gs_001.png", "rb") as f:
        r = client.post(
            "/verify",
            data=GS_001_APPLICATION,
            files={"image": ("gs_001.png", f, "image/png")},
        )
    assert b"Brand Name" in r.content       # human-readable field label
    assert b"Government Warning" in r.content


def test_verify_gs001_shows_processing_ms():
    with open(FIXTURES / "gs_001.png", "rb") as f:
        r = client.post(
            "/verify",
            data=GS_001_APPLICATION,
            files={"image": ("gs_001.png", f, "image/png")},
        )
    assert b"ms" in r.content.lower()       # timing row present
```

**Step 2: Run — confirm failure**

```bash
pytest tests/test_web.py::test_verify_gs001_shows_field_labels tests/test_web.py::test_verify_gs001_shows_processing_ms -v
```

Expected: FAIL — stub template doesn't render "Brand Name" or timing.

**Step 3: Replace result.html stub with the full template**

Create `app/templates/result.html`:

```html
{% set verdict_bg = {"match": "#16a34a", "mismatch": "#dc2626", "needs_review": "#d97706"} %}
{% set action_label = {"accept": "Accept", "manual_review": "Manual Review Required", "request_better_image": "Request Better Image"} %}
{% set status_color = {"match": "#16a34a", "mismatch": "#dc2626", "needs_review": "#d97706", "not_applicable": "#6b7280"} %}
{% set field_labels = {
    "brand_name": "Brand Name",
    "class_type": "Class / Type",
    "alcohol_content": "Alcohol Content",
    "net_contents": "Net Contents",
    "producer_name_address": "Producer Name & Address",
    "country_of_origin": "Country of Origin",
    "government_warning": "Government Warning"
} %}

<div style="margin-top:24px;">

  <!-- Verdict banner -->
  <div style="background:{{ verdict_bg.get(result.overall_verdict, '#6b7280') }};color:white;border-radius:8px;padding:20px 24px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;opacity:.8;margin-bottom:4px;">Overall Verdict</div>
      <div style="font-size:26px;font-weight:700;text-transform:capitalize;">{{ result.overall_verdict | replace("_", " ") }}</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:11px;opacity:.8;margin-bottom:4px;">Recommended Action</div>
      <div style="font-size:16px;font-weight:600;">{{ action_label.get(result.recommended_action, result.recommended_action) }}</div>
    </div>
  </div>

  <!-- Timing -->
  <p style="font-size:12px;color:#999;text-align:right;margin-bottom:16px;">Processed in {{ result.processing_ms }}ms</p>

  <!-- Field results -->
  <div style="background:white;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
    <div style="padding:16px 20px;border-bottom:1px solid #f0f0f0;">
      <h2 style="font-size:15px;font-weight:600;color:#333;">Field Results</h2>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <thead>
        <tr style="background:#f8f9fa;">
          <th style="text-align:left;padding:10px 20px;font-weight:600;color:#555;font-size:12px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #eee;">Field</th>
          <th style="text-align:left;padding:10px 16px;font-weight:600;color:#555;font-size:12px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #eee;">Status</th>
          <th style="text-align:left;padding:10px 16px;font-weight:600;color:#555;font-size:12px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #eee;">Details</th>
        </tr>
      </thead>
      <tbody>
        {% for field_name, fr in result.field_results.items() %}
        <tr style="border-bottom:1px solid #f5f5f5;">
          <td style="padding:12px 20px;font-weight:500;color:#222;white-space:nowrap;">{{ field_labels.get(field_name, field_name) }}</td>
          <td style="padding:12px 16px;white-space:nowrap;">
            <span style="background:{{ status_color.get(fr.status, '#6b7280') }}1a;color:{{ status_color.get(fr.status, '#6b7280') }};padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">
              {{ fr.status | replace("_", " ") | title }}
            </span>
          </td>
          <td style="padding:12px 16px;color:#555;">
            <span>{{ fr.explanation }}</span>
            {% if fr.status in ["mismatch", "needs_review"] and fr.get("observed_value") %}
            <div style="margin-top:5px;font-size:12px;color:#888;">
              Observed: <code style="background:#f5f5f5;padding:1px 5px;border-radius:3px;font-family:monospace;">{{ fr.observed_value[:120] }}{% if fr.observed_value|length > 120 %}…{% endif %}</code>
            </div>
            {% endif %}
            {% if fr.status == "mismatch" and fr.get("expected_value") %}
            <div style="margin-top:3px;font-size:12px;color:#bbb;">
              Expected: <code style="background:#f5f5f5;padding:1px 5px;border-radius:3px;font-family:monospace;">{{ fr.expected_value[:120] }}{% if fr.expected_value|length > 120 %}…{% endif %}</code>
            </div>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

</div>
```

**Step 4: Run — confirm pass**

```bash
pytest tests/test_web.py -v
```

Expected: all 13 tests PASS.

**Step 5: Commit**

```bash
git add app/templates/result.html tests/test_web.py
git commit -m "feat: result.html full fragment with verdict banner and field table"
```

---

## Task 9: Build complete index.html with HTMX

**Files:**
- Modify: `app/templates/index.html` (replace scaffold with final version)

**Step 1: Replace index.html scaffold with full reviewer form**

Replace the contents of `app/templates/index.html` entirely:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Alcohol Label Verifier</title>
  <script src="https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js" crossorigin="anonymous"></script>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f4f5f7;color:#1a1a1a;min-height:100vh}
    header{background:#1b3a6b;color:white;padding:14px 24px;display:flex;align-items:center;gap:12px}
    header h1{font-size:18px;font-weight:600}
    .scope-badge{background:rgba(255,255,255,.18);border-radius:20px;padding:3px 12px;font-size:12px;font-weight:500}
    .container{max-width:860px;margin:28px auto;padding:0 16px}
    .card{background:white;border:1px solid #e2e4e8;border-radius:8px;padding:22px 24px;margin-bottom:20px}
    .card-title{font-size:14px;font-weight:600;color:#444;margin-bottom:18px;padding-bottom:12px;border-bottom:1px solid #f0f0f0}
    .form-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .form-group{margin-bottom:14px}
    label.field-label{display:block;font-size:12px;font-weight:600;color:#666;margin-bottom:5px;text-transform:uppercase;letter-spacing:.04em}
    input[type=text],textarea,select{width:100%;padding:8px 11px;border:1px solid #d1d5db;border-radius:6px;font-size:14px;font-family:inherit;color:#111;background:#fff;transition:border-color .15s}
    input[type=text]:focus,textarea:focus{outline:none;border-color:#1b3a6b;box-shadow:0 0 0 3px rgba(27,58,107,.08)}
    textarea{resize:vertical;line-height:1.5}
    .upload-zone{border:2px dashed #c9cdd4;border-radius:8px;padding:28px 16px;text-align:center;cursor:pointer;transition:all .2s;background:#fafafa}
    .upload-zone:hover{border-color:#1b3a6b;background:#f0f4ff}
    .upload-zone p{font-size:14px;color:#888;margin-top:4px}
    .upload-zone .file-name{color:#1b3a6b;font-weight:600;font-size:15px}
    .upload-icon{font-size:32px;color:#c0c4cc;margin-bottom:8px}
    input[type=file]{display:none}
    .toggle-row{display:flex;align-items:center;gap:10px;margin-bottom:14px;padding:10px 12px;background:#f8f9fb;border-radius:6px}
    .toggle-row input[type=checkbox]{width:16px;height:16px;cursor:pointer;accent-color:#1b3a6b}
    .toggle-label{font-size:13px;font-weight:500;color:#444;cursor:pointer;user-select:none}
    #country-group{display:none;animation:fadeIn .2s}
    @keyframes fadeIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
    .run-btn{width:100%;background:#1b3a6b;color:white;border:none;border-radius:7px;padding:13px;font-size:15px;font-weight:600;cursor:pointer;letter-spacing:.01em;transition:background .15s}
    .run-btn:hover{background:#142e5a}
    .run-btn:active{background:#0f2347}
    .htmx-indicator{display:none}
    .htmx-indicator.htmx-request{display:block}
    #spinner{text-align:center;padding:28px;color:#888;font-size:14px}
    .spinner-dots{display:inline-block}
    .spinner-dots::after{content:".";animation:dots 1.2s steps(3,end) infinite}
    @keyframes dots{0%,20%{content:"."}40%,60%{content:".."}80%,100%{content:"..."}}
  </style>
</head>
<body>

<header>
  <h1>Alcohol Label Verifier</h1>
  <span class="scope-badge">Distilled Spirits</span>
</header>

<div class="container">

  <form enctype="multipart/form-data"
        hx-post="/verify"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#spinner">

    <!-- Image upload -->
    <div class="card">
      <div class="card-title">Label Image</div>
      <div class="upload-zone" id="upload-zone" onclick="document.getElementById('image-input').click()">
        <input type="file" id="image-input" name="image" accept="image/*" required onchange="onFileSelect(this)">
        <div class="upload-icon">&#128444;</div>
        <p id="upload-hint">Click to upload label image (PNG, JPG, TIFF)</p>
        <p id="file-name" class="file-name" style="display:none"></p>
      </div>
    </div>

    <!-- Expected application data -->
    <div class="card">
      <div class="card-title">Expected Application Data</div>

      <div class="form-row">
        <div class="form-group">
          <label class="field-label" for="brand_name">Brand Name</label>
          <input type="text" id="brand_name" name="brand_name" placeholder="e.g., OLD TOM DISTILLERY" required>
        </div>
        <div class="form-group">
          <label class="field-label" for="class_type">Class / Type</label>
          <input type="text" id="class_type" name="class_type" placeholder="e.g., Kentucky Straight Bourbon Whiskey" required>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label class="field-label" for="alcohol_content">Alcohol Content</label>
          <input type="text" id="alcohol_content" name="alcohol_content" placeholder="e.g., 40% Alc./Vol. (80 Proof)" required>
        </div>
        <div class="form-group">
          <label class="field-label" for="net_contents">Net Contents</label>
          <input type="text" id="net_contents" name="net_contents" placeholder="e.g., 750 mL" required>
        </div>
      </div>

      <div class="form-group">
        <label class="field-label" for="producer_name_address">Producer Name &amp; Address</label>
        <textarea id="producer_name_address" name="producer_name_address" rows="2"
                  placeholder="e.g., Old Tom Distillery, Louisville, KY" required></textarea>
      </div>

      <div class="toggle-row">
        <input type="checkbox" id="is_import" name="is_import" value="true" onchange="toggleImport(this)">
        <label class="toggle-label" for="is_import">This is an import product — country of origin required</label>
      </div>

      <div id="country-group" class="form-group">
        <label class="field-label" for="country_of_origin">Country of Origin</label>
        <input type="text" id="country_of_origin" name="country_of_origin" placeholder="e.g., Mexico">
      </div>

      <div class="form-group">
        <label class="field-label" for="government_warning">Government Warning</label>
        <textarea id="government_warning" name="government_warning" rows="4" required>GOVERNMENT WARNING: According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.</textarea>
      </div>
    </div>

    <button type="submit" class="run-btn">Run Verification</button>

  </form>

  <!-- Loading indicator (visible while htmx request in flight) -->
  <div id="spinner" class="htmx-indicator">
    <p>Verifying label<span class="spinner-dots"></span></p>
  </div>

  <!-- Result fragment injected here by HTMX -->
  <div id="result"></div>

</div>

<script>
  function onFileSelect(input) {
    if (!input.files.length) return;
    var file = input.files[0];
    document.getElementById("upload-hint").style.display = "none";
    var fn = document.getElementById("file-name");
    fn.textContent = file.name;
    fn.style.display = "block";
    document.getElementById("upload-zone").style.borderColor = "#1b3a6b";
  }

  function toggleImport(cb) {
    document.getElementById("country-group").style.display = cb.checked ? "block" : "none";
  }
</script>

</body>
</html>
```

**Step 2: Run tests to confirm they still pass**

```bash
pytest tests/test_web.py -v
```

Expected: all 13 tests PASS (the new index still contains `brand_name` and `Run Verification`).

**Step 3: Manual browser verification**

Start the server:

```bash
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` in a browser. Verify:
- [ ] Header shows "Alcohol Label Verifier" + "Distilled Spirits" badge
- [ ] Upload zone displays; clicking opens file picker
- [ ] Import toggle is visible; checking it reveals Country of Origin field
- [ ] Government Warning textarea is pre-filled
- [ ] Submitting with a gs_001.png fixture and the correct data shows a green "match" banner
- [ ] Submitting an unreadable fixture (e.g., gs_028.png — check cases.jsonl for unreadable cases) shows a yellow "needs review" banner
- [ ] Processing time appears in milliseconds
- [ ] Field table rows are color-coded

**Step 4: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: complete reviewer form with HTMX wiring and import toggle"
```

---

## Task 10: Update Dockerfile CMD

**Files:**
- Modify: `Dockerfile`

**Step 1: Change CMD to launch the web server**

In `Dockerfile`, replace:

```dockerfile
CMD ["python", "evals/run_golden_set.py"]
```

with:

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Verify the Dockerfile builds (optional, linux/amd64 only)**

On a Linux x86_64 host or with `--platform linux/amd64`:

```bash
docker build --platform linux/amd64 -t alc-verifier .
docker run --rm -p 8000:8000 alc-verifier
```

Open `http://localhost:8000/healthz` — expect `{"status":"ok"}`.

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore: update Dockerfile CMD to launch uvicorn web server"
```

---

## M2 Acceptance Checklist

Before marking M2 complete, verify all of the following:

- [ ] `pytest tests/ -v` — all tests PASS
- [ ] `python3 evals/run_golden_set.py` — all six gates `true`
- [ ] Browser: upload gs_001.png with correct data → green match banner, all fields match, processing_ms visible
- [ ] Browser: upload gs_003.png (import) with correct data → green banner, country_of_origin shows "Match"
- [ ] Browser: check import toggle → country_of_origin field appears/disappears
- [ ] Browser: submit with a wrong brand name → red mismatch banner, brand_name row shows "mismatch" with observed value
- [ ] Browser: submit an unreadable image (gs_025–gs_028 range) → yellow needs_review banner
- [ ] Government warning pre-fill is present and correct in the form
- [ ] Processing time is ≤ 5 seconds for typical readable fixtures on local hardware

---

## Summary of New Files

```
app/
  __init__.py
  main.py
  templates/
    index.html
    result.html
docs/
  plans/
    2026-04-16-m2-single-label-reviewer.md
tests/
  test_web.py
```

## Summary of Modified Files

```
alc_label_verifier/models.py       — FieldResult.observed_value added; _all_unreadable_result shape fixed
alc_label_verifier/matching.py     — observed_value populated in key matchers
alc_label_verifier/service.py      — processing_ms timing; observed_value serialised; _all_unreadable_result updated
alc_label_verifier/tests/test_integration.py — processing_ms integration test added
pyproject.toml                     — [web] optional deps added
Dockerfile                         — web extras installed; CMD changed to uvicorn
```

## Test Count by Task

| Task | New tests | Cumulative |
|------|-----------|------------|
| 5 | healthz ×2 | 2 |
| 6 | index ×2 | 4 |
| 7 | verify ×7 (match, mismatch, import, unreadable, oversized, returns_200, gs001_is_match) | 11 |
| 8 | field labels, processing_ms ×2 | 13 |
