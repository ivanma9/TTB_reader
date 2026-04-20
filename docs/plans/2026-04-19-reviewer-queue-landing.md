# Reviewer Queue Landing — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reframe the app around a reviewer work-queue — the landing page becomes a list of pre-paired application+label records with status badges, so the experience mirrors what Sarah/Dave/Jenny described in the interviews (open a queued application, check the label against the claim, record an action).

**Architecture:** A new in-memory `queue_state` module holds three seeded `QueueItem` records rehydrated from the existing `DEMO_CASES`. The landing route (`GET /`) renders the queue; `GET /queue/{id}` renders a read-only application + label workbench; `POST /queue/{id}/verify` runs the verifier; `POST /queue/{id}/action` records a reviewer decision and marks the item complete. Today's manual-entry form moves verbatim to `/test` as a secondary "bring your own label" affordance for evaluators. No schema, no persistence — all queue state resets on restart.

**Tech Stack:** FastAPI + Jinja2 templates (already in use), in-memory dict for queue state, existing PaddleOCR verifier untouched.

**Scope boundary:** Batch upload is **out of scope for this plan**. The `/batch` surface stays as-is; integrating it into the queue is a follow-up. Rationale: the single-reviewer queue flow is what the interviews most directly describe, and batch-to-queue refactor is a larger change that we should validate after the core queue experience is shipped.

**Non-goals:**
- Persistence across restarts
- Editing application fields on a queue item (that's only in `/test`)
- Multi-user / auth / audit log
- Batch intake integration

---

## Design decisions already locked

1. **Three seeded items only.** Same three cases as current `DEMO_CASES` (`gs_001`, `gs_003`, `gs_020`), each wrapped with fabricated queue metadata (submitter, application ID, submitted-at timestamp, import/domestic badge).
2. **Read-only on queue items.** The whole point is to mirror the TTB workflow where the application record is pre-populated by the applicant upstream. Editability lives on `/test`.
3. **Status model** (three top-level states; `complete` has three sub-states):
   - `pending` — not yet opened
   - `in_review` — verify has been run, reviewer has not yet recorded an action
   - `complete` with one of `approved` / `rejected` / `needs_better_image`
4. **Queue stays visible.** Completed items stay in the list with their badge — they do not disappear.
5. **Primary action is always through the queue.** `/test` is a small secondary link.

---

## File map

**Create:**
- `app/queue_state.py` — dataclass + in-memory store + seed function
- `app/templates/queue.html` — queue list view
- `app/templates/queue_item.html` — queue-item detail (read-only workbench)
- `app/templates/test.html` — manual-entry form (lifted from today's `index.html`)
- `tests/test_queue_state.py` — unit tests for the state module
- `tests/test_queue_web.py` — FastAPI route tests for the queue surface

**Modify:**
- `app/main.py` — replace `GET /` handler, add `/queue/{id}` routes, add `/test` + `/test/verify`
- `app/templates/index.html` — delete (replaced by queue.html + test.html)
- `app/static/workbench.css` — add queue table + status badge + action button styles
- `app/templates/batch.html` — update nav links only
- `app/templates/batch_workspace.html` — update nav links only
- `tests/test_web.py` — relocate form-flow tests from `/` → `/test`
- `scripts/smoke_test.sh` — add `GET /` (queue) + `GET /queue/gs_001` + `POST /queue/gs_001/verify` + `POST /queue/gs_001/action`
- `README.md` — update "Deployed demo" and "Guided demo path" sections
- `docs/approach.md` — add "Why queue-first" paragraph

---

## Task ordering (~11 tasks; 2–5 min each after the scaffolding task)

## Task 1: Queue state module with seeded items

**Files:**
- Create: `app/queue_state.py`
- Create: `tests/test_queue_state.py`

**Step 1: Write the failing test**

```python
# tests/test_queue_state.py
from __future__ import annotations

import pytest

from app.queue_state import (
    QueueItem,
    QueueStatus,
    ReviewerAction,
    get_item,
    list_items,
    reset_queue,
    seed_queue,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_queue()
    seed_queue()
    yield
    reset_queue()


class TestSeeding:
    def test_three_items_seeded(self):
        items = list_items()
        assert len(items) == 3

    def test_seeded_items_are_pending(self):
        for item in list_items():
            assert item.status == QueueStatus.PENDING

    def test_seeded_ids_match_demo_cases(self):
        ids = {item.id for item in list_items()}
        assert ids == {"gs_001", "gs_003", "gs_020"}

    def test_each_item_has_metadata(self):
        for item in list_items():
            assert item.submitter
            assert item.application_id.startswith("COLA-2026-")
            assert item.submitted_at
            assert item.beverage_class == "Distilled Spirits"
            assert item.origin_badge in {"Domestic", "Import"}

    def test_get_item_returns_seeded(self):
        assert get_item("gs_001") is not None

    def test_get_item_unknown_returns_none(self):
        assert get_item("nope") is None
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_queue_state.py -v`
Expected: FAIL with `ModuleNotFoundError: app.queue_state`

**Step 3: Write minimal implementation**

```python
# app/queue_state.py
"""In-memory queue of pre-paired application+label records for the reviewer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from app.demo_cases import DEMO_CASES


class QueueStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    COMPLETE = "complete"


class ReviewerAction(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_BETTER_IMAGE = "needs_better_image"


@dataclass
class QueueItem:
    id: str
    submitter: str
    application_id: str
    submitted_at: datetime
    beverage_class: str
    origin_badge: str  # "Domestic" or "Import"
    image_path: Path
    form_values: dict[str, str | None]
    status: QueueStatus = QueueStatus.PENDING
    verdict: Optional[dict] = None
    reviewer_action: Optional[ReviewerAction] = None
    completed_at: Optional[datetime] = None


_QUEUE: dict[str, QueueItem] = {}


# Fabricated metadata — stable so tests and screenshots stay reproducible.
_METADATA = {
    "gs_001": {
        "submitter": "Old Tom Distillery LLC",
        "application_id": "COLA-2026-0412-001",
        "submitted_at": datetime(2026, 4, 12, 9, 14),
        "origin_badge": "Domestic",
    },
    "gs_003": {
        "submitter": "Sierra Azul Imports",
        "application_id": "COLA-2026-0413-027",
        "submitted_at": datetime(2026, 4, 13, 14, 02),
        "origin_badge": "Import",
    },
    "gs_020": {
        "submitter": "Old Tom Distillery LLC",
        "application_id": "COLA-2026-0415-009",
        "submitted_at": datetime(2026, 4, 15, 11, 47),
        "origin_badge": "Domestic",
    },
}


def reset_queue() -> None:
    _QUEUE.clear()


def seed_queue() -> None:
    if _QUEUE:
        return
    for case_id, case in DEMO_CASES.items():
        meta = _METADATA[case_id]
        _QUEUE[case_id] = QueueItem(
            id=case_id,
            submitter=meta["submitter"],
            application_id=meta["application_id"],
            submitted_at=meta["submitted_at"],
            beverage_class="Distilled Spirits",
            origin_badge=meta["origin_badge"],
            image_path=case["image_path"],
            form_values=dict(case["form_values"]),
        )


def list_items() -> list[QueueItem]:
    return list(_QUEUE.values())


def get_item(item_id: str) -> Optional[QueueItem]:
    return _QUEUE.get(item_id)


def mark_in_review(item_id: str, verdict: dict) -> Optional[QueueItem]:
    item = _QUEUE.get(item_id)
    if item is None:
        return None
    item.status = QueueStatus.IN_REVIEW
    item.verdict = verdict
    return item


def mark_complete(item_id: str, action: ReviewerAction) -> Optional[QueueItem]:
    item = _QUEUE.get(item_id)
    if item is None:
        return None
    item.status = QueueStatus.COMPLETE
    item.reviewer_action = action
    item.completed_at = datetime.now()
    return item
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_queue_state.py -v`
Expected: PASS (6/6)

**Step 5: Commit**

```bash
git add app/queue_state.py tests/test_queue_state.py
git commit -m "feat: queue_state module with three seeded items"
```

---

## Task 2: Status-transition tests for queue_state

**Files:**
- Modify: `tests/test_queue_state.py`

**Step 1: Append status-transition tests**

```python
# tests/test_queue_state.py (append)
from app.queue_state import mark_complete, mark_in_review


class TestTransitions:
    def test_mark_in_review_sets_verdict(self):
        item = mark_in_review("gs_001", {"overall_verdict": "match"})
        assert item.status == QueueStatus.IN_REVIEW
        assert item.verdict == {"overall_verdict": "match"}

    def test_mark_complete_sets_action_and_timestamp(self):
        mark_in_review("gs_001", {"overall_verdict": "match"})
        item = mark_complete("gs_001", ReviewerAction.APPROVED)
        assert item.status == QueueStatus.COMPLETE
        assert item.reviewer_action == ReviewerAction.APPROVED
        assert item.completed_at is not None

    def test_unknown_id_returns_none(self):
        assert mark_in_review("nope", {}) is None
        assert mark_complete("nope", ReviewerAction.APPROVED) is None
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/test_queue_state.py -v`
Expected: PASS (9/9)

**Step 3: Commit**

```bash
git add tests/test_queue_state.py
git commit -m "test: queue_state transitions"
```

---

## Task 3: Queue landing route replaces today's `/`

**Files:**
- Modify: `app/main.py` (replace `GET /` handler; import queue_state)
- Create: `app/templates/queue.html`
- Create: `tests/test_queue_web.py`

**Step 1: Write the failing test**

```python
# tests/test_queue_web.py
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.queue_state import reset_queue, seed_queue


@pytest.fixture(autouse=True)
def _reset():
    reset_queue()
    seed_queue()
    yield
    reset_queue()


@pytest.fixture(scope="module")
def client():
    with patch("app.main.warm_ocr"):
        from app.main import app
        return TestClient(app, raise_server_exceptions=True)


class TestQueueLanding:
    def test_landing_is_queue(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Review Queue" in r.text

    def test_landing_shows_three_items(self, client):
        r = client.get("/")
        assert "OLD TOM DISTILLERY" in r.text  # gs_001 + gs_020 submitter text
        assert "Sierra Azul Imports" in r.text  # gs_003

    def test_landing_shows_pending_badges(self, client):
        r = client.get("/")
        # three items, all pending on a fresh seed
        assert r.text.count("Pending") >= 3

    def test_landing_shows_application_ids(self, client):
        r = client.get("/")
        assert "COLA-2026-0412-001" in r.text

    def test_landing_links_to_items(self, client):
        r = client.get("/")
        assert '/queue/gs_001' in r.text
        assert '/queue/gs_003' in r.text
        assert '/queue/gs_020' in r.text
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_queue_web.py -v`
Expected: FAIL (landing text has no "Review Queue")

**Step 3: Write the template**

```html
<!-- app/templates/queue.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Review Queue — Compliance Auditor</title>
  <link rel="stylesheet" href="/static/workbench.css" />
</head>
<body>

<header class="app-header">
  <span class="app-icon">⚖</span>
  <span class="app-title">Compliance Auditor</span>
  <nav class="app-nav">
    <a href="/" class="nav-link nav-link--active">Review Queue</a>
    <a href="/test" class="nav-link">Test a label</a>
    <a href="/batch" class="nav-link">Batch intake</a>
  </nav>
</header>

<main>
  <section>
    <h1 class="page-heading">Review Queue</h1>
    <span class="scope-badge">Distilled Spirits</span>
    <p class="queue-hint">
      Queued applications awaiting label-to-application verification.
      Open an application, run verification against its label, and record your action.
    </p>
  </section>

  <div class="card">
    <table class="queue-table">
      <thead>
        <tr>
          <th>Application</th>
          <th>Submitter</th>
          <th>Submitted</th>
          <th>Origin</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for item in items %}
          <tr class="queue-row">
            <td class="queue-app-id">{{ item.application_id }}</td>
            <td>{{ item.submitter }}</td>
            <td>{{ item.submitted_at.strftime("%Y-%m-%d %H:%M") }}</td>
            <td>
              <span class="origin-badge origin-badge--{{ item.origin_badge|lower }}">
                {{ item.origin_badge }}
              </span>
            </td>
            <td>
              {% include "_status_badge.html" %}
            </td>
            <td>
              <a class="btn-secondary" href="/queue/{{ item.id }}">Open</a>
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</main>

</body>
</html>
```

```html
<!-- app/templates/_status_badge.html -->
{% if item.status.value == "pending" %}
  <span class="status-badge status-badge--pending">Pending</span>
{% elif item.status.value == "in_review" %}
  <span class="status-badge status-badge--in-review">In review</span>
{% elif item.status.value == "complete" and item.reviewer_action %}
  {% if item.reviewer_action.value == "approved" %}
    <span class="status-badge status-badge--approved">Complete · Approved</span>
  {% elif item.reviewer_action.value == "rejected" %}
    <span class="status-badge status-badge--rejected">Complete · Rejected</span>
  {% elif item.reviewer_action.value == "needs_better_image" %}
    <span class="status-badge status-badge--needs-image">Complete · Needs better image</span>
  {% endif %}
{% endif %}
```

**Step 4: Update `app/main.py`**

Replace the existing `@app.get("/")` handler with:

```python
# app/main.py (replace index handler)
from app.queue_state import list_items, seed_queue

# ... inside lifespan:
@asynccontextmanager
async def lifespan(application: FastAPI):
    warm_ocr()
    seed_queue()
    yield


@app.get("/", response_class=HTMLResponse)
async def queue_landing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="queue.html",
        context={"items": list_items()},
    )
```

Delete the old `index.html` references from the handler (they'll be re-created in Task 7 under a `/test` route). For now `/test` does not yet exist; that's Task 7. Keep `/demo/{case_id}` and `/verify` intact — they will be removed in Task 7.

**Step 5: Run tests**

Run: `python3 -m pytest tests/test_queue_web.py::TestQueueLanding -v`
Expected: PASS (5/5)

**Step 6: Commit**

```bash
git add app/main.py app/templates/queue.html app/templates/_status_badge.html tests/test_queue_web.py
git commit -m "feat: queue landing replaces single-label index"
```

---

## Task 4: Queue-item detail view (read-only)

**Files:**
- Modify: `app/main.py` (add `GET /queue/{id}`)
- Create: `app/templates/queue_item.html`
- Modify: `tests/test_queue_web.py`

**Step 1: Write the failing test**

```python
# tests/test_queue_web.py (append)
class TestQueueItemDetail:
    def test_renders_application_fields_readonly(self, client):
        r = client.get("/queue/gs_001")
        assert r.status_code == 200
        assert "OLD TOM DISTILLERY" in r.text
        assert "Kentucky Straight Bourbon Whiskey" in r.text
        # read-only: fields appear as <dd> or similar, not <input>
        assert '<input class="field-input"' not in r.text

    def test_shows_image(self, client):
        r = client.get("/queue/gs_001")
        assert "/queue/gs_001/image" in r.text

    def test_has_verify_button(self, client):
        r = client.get("/queue/gs_001")
        assert 'action="/queue/gs_001/verify"' in r.text

    def test_unknown_id_404(self, client):
        r = client.get("/queue/nope")
        assert r.status_code == 404
```

**Step 2: Run — expect FAIL**

**Step 3: Add handler + template + image-serving route**

```python
# app/main.py (add)
from fastapi.responses import FileResponse
from app.queue_state import get_item

@app.get("/queue/{item_id}", response_class=HTMLResponse)
async def queue_item_detail(request: Request, item_id: str) -> HTMLResponse:
    item = get_item(item_id)
    if item is None:
        return HTMLResponse(status_code=404, content="Queue item not found.")
    return templates.TemplateResponse(
        request=request,
        name="queue_item.html",
        context={
            "item": item,
            "field_labels": FIELD_LABELS,
            "reason_explanations": REASON_EXPLANATIONS,
            "standard_warning": STANDARD_WARNING,
        },
    )


@app.get("/queue/{item_id}/image")
async def queue_item_image(item_id: str) -> FileResponse:
    item = get_item(item_id)
    if item is None:
        return HTMLResponse(status_code=404, content="Not found.")
    return FileResponse(path=str(item.image_path))
```

```html
<!-- app/templates/queue_item.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ item.application_id }} — Compliance Auditor</title>
  <link rel="stylesheet" href="/static/workbench.css" />
</head>
<body>

<header class="app-header">
  <span class="app-icon">⚖</span>
  <span class="app-title">Compliance Auditor</span>
  <nav class="app-nav">
    <a href="/" class="nav-link">Review Queue</a>
    <a href="/test" class="nav-link">Test a label</a>
    <a href="/batch" class="nav-link">Batch intake</a>
  </nav>
</header>

<main>
  <nav class="breadcrumb"><a href="/">← Back to queue</a></nav>

  <section class="item-header">
    <h1 class="page-heading">{{ item.application_id }}</h1>
    <div class="item-meta">
      <span>Submitter: {{ item.submitter }}</span>
      <span>Submitted: {{ item.submitted_at.strftime("%Y-%m-%d %H:%M") }}</span>
      <span class="origin-badge origin-badge--{{ item.origin_badge|lower }}">
        {{ item.origin_badge }}
      </span>
      {% include "_status_badge.html" %}
    </div>
  </section>

  <div class="item-grid">

    <!-- Label image -->
    <div class="card">
      <p class="card-section-label">Label artwork</p>
      <img src="/queue/{{ item.id }}/image" alt="Label for {{ item.application_id }}" class="label-image" />
    </div>

    <!-- Application record (read-only) -->
    <div class="card">
      <p class="card-section-label">Application record</p>
      <dl class="application-record">
        <dt>Brand Name</dt><dd>{{ item.form_values.brand_name }}</dd>
        <dt>Class / Type</dt><dd>{{ item.form_values.class_type }}</dd>
        <dt>Alcohol Content</dt><dd>{{ item.form_values.alcohol_content }}</dd>
        <dt>Net Contents</dt><dd>{{ item.form_values.net_contents }}</dd>
        <dt>Producer / Address</dt><dd>{{ item.form_values.producer_name_address }}</dd>
        {% if item.form_values.is_import %}
          <dt>Country of Origin</dt><dd>{{ item.form_values.country_of_origin }}</dd>
        {% endif %}
        <dt>Government Warning</dt><dd class="warning-text">{{ item.form_values.government_warning }}</dd>
      </dl>
    </div>
  </div>

  {% if not item.verdict %}
    <form method="post" action="/queue/{{ item.id }}/verify">
      <button type="submit" class="btn-primary">Run Verification</button>
    </form>
  {% endif %}

  {% if item.verdict %}
    <div class="card">
      <p class="card-section-label">Verification result</p>
      {% set result = item.verdict %}
      {% include "_result_panel.html" %}
    </div>

    {% if item.status.value == "in_review" %}
      <div class="card">
        <p class="card-section-label">Record action</p>
        <form method="post" action="/queue/{{ item.id }}/action" class="action-row">
          <button type="submit" name="action" value="approved" class="btn-approve">Approve</button>
          <button type="submit" name="action" value="rejected" class="btn-reject">Reject</button>
          <button type="submit" name="action" value="needs_better_image" class="btn-needs-image">Request better image</button>
        </form>
      </div>
    {% endif %}
  {% endif %}

</main>
</body>
</html>
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_queue_web.py::TestQueueItemDetail -v`
Expected: PASS (4/4)

**Step 5: Commit**

```bash
git add app/main.py app/templates/queue_item.html tests/test_queue_web.py
git commit -m "feat: queue item detail view with read-only application record"
```

---

## Task 5: `POST /queue/{id}/verify` runs verifier and sets in_review

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_queue_web.py`

**Step 1: Write the failing test**

```python
# tests/test_queue_web.py (append)
from unittest.mock import patch


class TestQueueItemVerify:
    def test_verify_runs_and_transitions_to_in_review(self, client):
        stub = {
            "overall_verdict": "match",
            "recommended_action": "accept",
            "field_results": [],
            "processing_ms": 123,
        }
        with patch("app.main.verify_label", return_value=stub):
            r = client.post("/queue/gs_001/verify")
        assert r.status_code == 200
        assert "Verification result" in r.text
        # In-review items must now show action buttons
        assert 'value="approved"' in r.text
        assert 'value="rejected"' in r.text

    def test_verify_unknown_id_404(self, client):
        r = client.post("/queue/nope/verify")
        assert r.status_code == 404
```

**Step 2: Run — expect FAIL**

**Step 3: Add handler**

```python
# app/main.py (add)
from app.queue_state import mark_in_review

@app.post("/queue/{item_id}/verify", response_class=HTMLResponse)
async def queue_item_verify(request: Request, item_id: str) -> HTMLResponse:
    item = get_item(item_id)
    if item is None:
        return HTMLResponse(status_code=404, content="Queue item not found.")

    application = build_application_payload(item.form_values)
    result = verify_label(str(item.image_path), application)

    updated = mark_in_review(item_id, result)

    return templates.TemplateResponse(
        request=request,
        name="queue_item.html",
        context={
            "item": updated,
            "field_labels": FIELD_LABELS,
            "reason_explanations": REASON_EXPLANATIONS,
            "standard_warning": STANDARD_WARNING,
        },
    )
```

**Step 4: Run tests — expect PASS**

**Step 5: Commit**

```bash
git add app/main.py tests/test_queue_web.py
git commit -m "feat: verify endpoint transitions queue item to in_review"
```

---

## Task 6: `POST /queue/{id}/action` records reviewer decision

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_queue_web.py`

**Step 1: Write the failing test**

```python
# tests/test_queue_web.py (append)
class TestQueueItemAction:
    def test_action_marks_complete_and_redirects(self, client):
        stub = {"overall_verdict": "match", "recommended_action": "accept", "field_results": []}
        with patch("app.main.verify_label", return_value=stub):
            client.post("/queue/gs_001/verify")

        r = client.post("/queue/gs_001/action", data={"action": "approved"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"

        # Queue landing reflects the completion
        r = client.get("/")
        assert "Complete · Approved" in r.text

    def test_action_rejected_shows_on_queue(self, client):
        stub = {"overall_verdict": "mismatch", "recommended_action": "manual_review", "field_results": []}
        with patch("app.main.verify_label", return_value=stub):
            client.post("/queue/gs_003/verify")
        client.post("/queue/gs_003/action", data={"action": "rejected"}, follow_redirects=False)
        r = client.get("/")
        assert "Complete · Rejected" in r.text

    def test_action_invalid_value_rejected(self, client):
        r = client.post("/queue/gs_001/action", data={"action": "bogus"})
        assert r.status_code == 422

    def test_action_unknown_id_404(self, client):
        r = client.post("/queue/nope/action", data={"action": "approved"})
        assert r.status_code == 404
```

**Step 2: Run — expect FAIL**

**Step 3: Add handler**

```python
# app/main.py (add)
from app.queue_state import ReviewerAction, mark_complete

_VALID_ACTIONS = {a.value for a in ReviewerAction}

@app.post("/queue/{item_id}/action")
async def queue_item_action(item_id: str, action: Annotated[str, Form()]) -> RedirectResponse:
    if action not in _VALID_ACTIONS:
        return JSONResponse(status_code=422, content={"error": "Unknown action."})
    if get_item(item_id) is None:
        return HTMLResponse(status_code=404, content="Queue item not found.")
    mark_complete(item_id, ReviewerAction(action))
    return RedirectResponse(url="/", status_code=303)
```

**Step 4: Run tests — expect PASS**

**Step 5: Commit**

```bash
git add app/main.py tests/test_queue_web.py
git commit -m "feat: reviewer action endpoint marks queue item complete"
```

---

## Task 7: Move manual-entry form to `/test`

**Files:**
- Create: `app/templates/test.html` (lifted verbatim from today's `index.html`; swap nav active state + replace post target with `/test/verify`)
- Modify: `app/main.py` (add `GET /test`, `POST /test/verify`; remove old `/`, `/demo/{case_id}`, `/verify`)
- Delete: `app/templates/index.html`

**Step 1: Copy `app/templates/index.html` → `app/templates/test.html`.**

Update three things in `test.html`:
1. Page title: `<title>Test a label — Compliance Auditor</title>`
2. Nav: mark `Test a label` as active:
   ```html
   <a href="/" class="nav-link">Review Queue</a>
   <a href="/test" class="nav-link nav-link--active">Test a label</a>
   <a href="/batch" class="nav-link">Batch intake</a>
   ```
3. Form action: `<form method="post" action="/test/verify" enctype="multipart/form-data" id="verify-form" novalidate>`
4. Remove the `{% if demo_cases %}` block entirely (demo cards no longer needed here).
5. Replace `<h1 class="page-heading">Reviewer Workstation</h1>` with `<h1 class="page-heading">Test a label</h1>` and add:
   ```html
   <p class="test-hint">
     Bring-your-own flow for evaluators. In the real TTB workflow, application
     fields come from the applicant's COLA submission — the reviewer never
     types them. This surface exists so you can poke the verifier at arbitrary
     inputs.
   </p>
   ```

**Step 2: Update `app/main.py`.**

Replace the `/verify` handler with `/test/verify`; add `GET /test`. Delete `GET /` (replaced in Task 3), delete `POST /demo/{case_id}`.

```python
# app/main.py
@app.get("/test", response_class=HTMLResponse)
async def test_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="test.html",
        context={
            "standard_warning": STANDARD_WARNING,
            "result": None,
            "errors": {},
            "form_values": {},
        },
    )


@app.post("/test/verify", response_class=HTMLResponse)
async def test_verify(
    request: Request,
    label_image: Annotated[Optional[UploadFile], File()] = None,
    brand_name: Annotated[str, Form()] = "",
    class_type: Annotated[str, Form()] = "",
    alcohol_content: Annotated[str, Form()] = "",
    net_contents: Annotated[str, Form()] = "",
    producer_name_address: Annotated[str, Form()] = "",
    is_import: Annotated[Optional[str], Form()] = None,
    country_of_origin: Annotated[str, Form()] = "",
    government_warning: Annotated[str, Form()] = "",
) -> HTMLResponse:
    # (body lifted verbatim from the old /verify handler, with
    # `name="index.html"` → `name="test.html"` and `demo_cases`/`active_demo`
    # context keys removed.)
    ...
```

**Step 3: Delete `app/templates/index.html`.**

```bash
git rm app/templates/index.html
```

**Step 4: Write the test.**

```python
# tests/test_queue_web.py (append)
class TestManualTestSurface:
    def test_get_test_renders_form(self, client):
        r = client.get("/test")
        assert r.status_code == 200
        assert "Test a label" in r.text
        assert 'action="/test/verify"' in r.text

    def test_post_test_verify_requires_image(self, client):
        r = client.post("/test/verify", data={"brand_name": "X"})
        assert r.status_code == 422
        assert "Label image is required" in r.text
```

**Step 5: Run tests**

Run: `python3 -m pytest tests/test_queue_web.py -v`
Expected: PASS on new tests. Existing `tests/test_web.py` will fail — Task 9 fixes that.

**Step 6: Commit**

```bash
git add app/main.py app/templates/test.html
git rm app/templates/index.html
git add tests/test_queue_web.py
git commit -m "feat: move manual-entry form to /test"
```

---

## Task 8: CSS polish for queue table + status badges + action buttons

**Files:**
- Modify: `app/static/workbench.css`

Add these blocks (place near the top, after the existing header rules). Values use the existing CSS-variable palette — keep it consistent.

```css
/* ── Queue table ─────────────────────────────────────── */
.queue-hint {
  color: var(--text-muted, #5a6472);
  margin: 0.5rem 0 1.5rem;
}
.queue-table {
  width: 100%;
  border-collapse: collapse;
}
.queue-table th {
  text-align: left;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted, #5a6472);
  border-bottom: 1px solid var(--border, #e4e7eb);
  padding: 0.75rem 1rem;
}
.queue-table td {
  padding: 1rem;
  border-bottom: 1px solid var(--border, #e4e7eb);
  vertical-align: middle;
}
.queue-app-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 600;
}

/* ── Status badges ───────────────────────────────────── */
.status-badge {
  display: inline-block;
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
}
.status-badge--pending       { background: #eef2f7; color: #51607a; }
.status-badge--in-review     { background: #fff4d6; color: #8a6a08; }
.status-badge--approved      { background: #d7f5df; color: #186a3b; }
.status-badge--rejected      { background: #fde2e2; color: #8a2c2c; }
.status-badge--needs-image   { background: #ffe4cc; color: #8a4a12; }

.origin-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}
.origin-badge--domestic { background: #e8eefc; color: #2546a8; }
.origin-badge--import   { background: #f2e8fc; color: #5e2ca8; }

/* ── Queue item detail ───────────────────────────────── */
.breadcrumb { margin-bottom: 1rem; }
.item-header { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.5rem; }
.item-meta { display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; font-size: 0.9rem; color: var(--text-muted, #5a6472); }
.item-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }
@media (max-width: 960px) { .item-grid { grid-template-columns: 1fr; } }
.label-image { max-width: 100%; border-radius: 6px; }
.application-record { display: grid; grid-template-columns: max-content 1fr; column-gap: 1.5rem; row-gap: 0.6rem; }
.application-record dt { font-weight: 600; color: var(--text-muted, #5a6472); }
.application-record dd { margin: 0; }
.warning-text { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; white-space: pre-wrap; }

/* ── Action buttons ──────────────────────────────────── */
.action-row { display: flex; gap: 0.75rem; }
.btn-approve, .btn-reject, .btn-needs-image {
  padding: 0.6rem 1.2rem;
  border: 0;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}
.btn-approve   { background: #186a3b; color: white; }
.btn-reject    { background: #8a2c2c; color: white; }
.btn-needs-image { background: #8a4a12; color: white; }

/* ── Test page hint ──────────────────────────────────── */
.test-hint {
  background: #fff9e6;
  border-left: 3px solid #d4a017;
  padding: 0.75rem 1rem;
  margin: 1rem 0 1.5rem;
  font-size: 0.9rem;
}
```

**No tests for pure CSS. Smoke test below covers that styles load.**

**Commit:**

```bash
git add app/static/workbench.css
git commit -m "feat: queue + status badge styles"
```

---

## Task 9: Repoint `tests/test_web.py` at `/test`

**Files:**
- Modify: `tests/test_web.py`

The existing tests for `/` and `/verify` now target `/test` and `/test/verify`. The tests that asserted demo-card presence on `/` should move to `tests/test_queue_web.py::TestQueueLanding` — but since the queue replaces the demo cards entirely, those assertions become irrelevant and should be deleted rather than migrated.

**Step 1: Global replace in `tests/test_web.py`:**
- `client.get("/")` → `client.get("/test")`
- `client.post("/verify", …)` → `client.post("/test/verify", …)`
- `client.post("/demo/gs_001")` → DELETE the demo-case tests (the queue covers that flow now)

**Step 2: Update class names for clarity:**
- `TestIndexPage` → `TestTestSurfacePage`
- Replace assertion `"Reviewer Workstation" in r.text` with `"Test a label" in r.text`
- Delete `test_index_has_scope_badge` (scope badge is on the queue page now; covered by `test_queue_web.py`)

**Step 3: Run full suite**

Run: `python3 -m pytest tests/test_web.py tests/test_queue_web.py tests/test_queue_state.py -v`
Expected: all green.

**Step 4: Commit**

```bash
git add tests/test_web.py
git commit -m "test: retarget web tests at /test surface"
```

---

## Task 10: Smoke test covers queue flow

**Files:**
- Modify: `scripts/smoke_test.sh`

Replace the old `POST /demo/gs_001` probe with:

```bash
# Queue landing
curl -fsS "${BASE}/" | grep -q "Review Queue" || { echo "queue landing missing"; exit 1; }

# Queue item detail
curl -fsS "${BASE}/queue/gs_001" | grep -q "COLA-2026-0412-001" || { echo "queue item detail missing"; exit 1; }

# Verify through the queue
curl -fsS -X POST "${BASE}/queue/gs_001/verify" -o /dev/null || { echo "queue verify failed"; exit 1; }

# Record action
curl -fsS -o /dev/null -w "%{http_code}" -X POST \
  -d "action=approved" \
  "${BASE}/queue/gs_001/action" | grep -q "303" || { echo "action endpoint failed"; exit 1; }

# /test renders
curl -fsS "${BASE}/test" | grep -q "Test a label" || { echo "/test missing"; exit 1; }
```

Run: `bash scripts/smoke_test.sh` locally.
Expected: all probes green.

**Commit:**

```bash
git add scripts/smoke_test.sh
git commit -m "chore: smoke test covers queue + /test surfaces"
```

---

## Task 11: README + approach.md

**Files:**
- Modify: `README.md`
- Modify: `docs/approach.md`

**Step 1: `README.md` — replace the "Guided demo path" section**

```markdown
## Guided demo path

The landing page is a **review queue** — three pre-paired application+label
records awaiting verification. For each one, a reviewer would:

1. Open the application from the queue.
2. Run verification — the verifier compares the label OCR against the
   application record.
3. Record an action: **Approve**, **Reject**, or **Request better image**.

The three seeded items:

| Application | Case | What it shows |
|---|---|---|
| `COLA-2026-0412-001` | Clean domestic match | Every field matches — expected verdict `match`, recommended action `Approve`. |
| `COLA-2026-0413-027` | Import with country of origin | Exercises the import conditional rule — expected verdict `match`. |
| `COLA-2026-0415-009` | Needs review (occluded warning) | OCR can't read the warning — expected verdict `needs_review`, recommended action `Request better image`. |

Status badges persist in memory for the life of the process; restarting the
app resets all items back to `Pending`.

### Bring-your-own label

For evaluators who want to poke the verifier at arbitrary inputs, the
**Test a label** tab (top nav) keeps the manual-entry form: upload any
label image and type the application values by hand.

In production, application fields would come from COLA — reviewers would
never type them. The `/test` surface exists only for exploration; it does
not add items to the queue.
```

**Step 2: `docs/approach.md` — add a paragraph after "Architecture at a glance"**

```markdown
## Why queue-first

The three reviewer interviews (Sarah, Dave, Jenny) describe the same flow:
open an **existing** application, see the **already-populated** fields
alongside the label artwork, record a decision. Reviewers never type the
application values themselves — those come from the applicant upstream via
COLA.

The landing page was originally a single-form workbench with three demo
cards. That framing put the reviewer in the wrong role. Queue-first moves
the primary affordance to a list of pre-paired records and reserves the
manual-entry form (now `/test`) as a secondary exploration surface.

This is a UX decision, not a data-model change — the underlying verifier
still takes an image path and an application payload and returns a
structured verdict.
```

**Step 3: Commit**

```bash
git add README.md docs/approach.md
git commit -m "docs: queue-first landing flow"
```

---

## Verification before done

Before considering the plan complete, run:

```bash
python3 -m pytest tests/test_queue_state.py tests/test_queue_web.py tests/test_web.py -v
python3 -m pytest   # full suite
bash scripts/smoke_test.sh
```

Then open http://localhost:8000 in a browser and exercise:
1. Queue landing shows three `Pending` items.
2. Click `Open` on the first item → read-only application record + label image render.
3. Click `Run Verification` → result panel appears, status changes to `In review`, three action buttons appear.
4. Click `Approve` → redirects to queue, item shows `Complete · Approved`.
5. Repeat for gs_020 → verdict `needs_review`, choose `Request better image` → status updates accordingly.
6. Navigate to `Test a label` tab → manual form still works.
7. Refresh the process (Docker: `docker run` again; local: restart uvicorn) → queue resets to all `Pending`.

If any of 1–7 fails, fix the offending task before claiming done.

After verification passes, **invoke `superpowers:requesting-code-review`** per CLAUDE.md's mandatory post-implementation review rule.

---

## Deferred (explicit non-scope)

- **Batch-to-queue integration.** The existing `/batch` surface stays as-is. Wiring batch uploads to create queue items is a follow-up plan.
- **Persistence.** In-memory only; survives no restarts.
- **Auth / audit log.** Prototype; open access.
- **Editable application on queue items.** Deliberate — mirrors the real workflow where the application is what the applicant submitted, not what the reviewer types.
