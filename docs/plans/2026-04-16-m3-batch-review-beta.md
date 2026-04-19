# M3 Batch Review Beta — Implementation Plan

**Goal:** Extend the existing FastAPI + Jinja single-label reviewer app with a separate batch workflow that accepts up to 10 label images, lets the reviewer enter expected data per row, shows a visible sequential queue while rows are processed, and renders a batch summary plus per-row drill-down without regressing the completed M2 single-label path.

**Architecture:** Keep the existing single-label flow at `/` and `POST /verify` intact. Add a staged, session-scoped batch workspace:

- `GET /batch` renders the batch upload entry page.
- `POST /batch/session` accepts the selected files, enforces batch upload limits, stages the files into a temp batch directory, creates a process-local batch record, and redirects to `GET /batch/{batch_id}`.
- `GET /batch/{batch_id}` renders the batch workspace with row editors and queue state.
- `POST /batch/{batch_id}/run` validates per-row expected data without requiring the user to re-upload files. On validation errors it re-renders the same workspace with row errors; on success it marks the batch as queued and returns the workspace with client-side polling enabled.
- `POST /batch/{batch_id}/process-next` processes exactly one pending row synchronously, updates batch state, and returns updated queue markup or JSON for the polling loop.

This preserves a visible sequential queue without introducing a hidden background worker. The browser drives progression one row at a time, and the server keeps only session-scoped temp files plus in-memory batch metadata for the lifetime of the workspace.

**Tech Stack:** Python 3.11, FastAPI, Jinja2, vanilla JavaScript, existing local CSS, existing `alc_label_verifier` package. No new runtime dependencies are required for M3.

**M1/M2 status:** Complete. Do not change the verifier contract, beverage scope, tracked field set, or the single-label verdict and recommended-action semantics established in M1 and M2.

---

## Locked Beta Decisions

- Keep batch as a distinct route family instead of folding it into `/`. This protects the finished M2 path from UI and validation churn.
- Use a server-staged batch workspace. Files are uploaded once to a temp batch directory, and row form state lives in a process-local batch record keyed by a random batch ID.
- Treat the process-local batch store as acceptable for the local beta and take-home demo. It is not intended as a production multi-worker design.
- Show a visible queue by processing one row per `POST /batch/{batch_id}/process-next` request. Do not hide batch execution behind one long blocking request.
- Keep row-data validation separate from file upload. Once files are staged, the reviewer can fix validation errors and retry without reselecting images.
- Enforce explicit upload limits at batch staging time:
  - maximum `10` files per batch
  - maximum `20 MB` per file
  - maximum `100 MB` total staged bytes across the whole batch
- Preserve the existing `verify_label` result shape for successful rows. Batch adds queue state, summary data, and workspace orchestration around that result.
- Represent unexpected row-processing failures as a distinct batch row `processing_error` state. Do not fabricate field-level `unreadable` results for system failures.
- Roll `processing_error` rows up under the batch `needs_review` summary count, but surface them separately in the UI and metrics as system errors.
- Do not implement CSV import, export generation, background workers, or cross-session batch persistence in beta.

---

## Route and State Design

### Routes

- `GET /`
  - Existing single-label page. No functional behavior change.
- `POST /verify`
  - Existing single-label verification endpoint. Only refactor shared helpers if needed; preserve current behavior and status codes.
- `GET /batch`
  - New batch entry page with multi-file upload and empty-state guidance.
- `POST /batch/session`
  - Stages files, enforces file count and size limits, creates the batch workspace, and redirects to `GET /batch/{batch_id}`.
- `GET /batch/{batch_id}`
  - Renders the batch workspace, including row editors, current queue state, summary area, and any validation errors.
- `POST /batch/{batch_id}/run`
  - Validates the expected-data rows for the staged files. On success, flips the workspace into queued mode and returns a page that starts polling `process-next`.
- `POST /batch/{batch_id}/process-next`
  - Processes exactly one queued row, updates summary and row state, and returns the updated status fragment or JSON payload used by the polling loop.

### Batch Workspace State

Each active batch should have a process-local state object similar to:

```python
{
    "batch_id": "b_abc123",
    "created_at": 1713310000.0,
    "expires_at": 1713311800.0,
    "status": "draft",  # draft | queued | running | complete
    "temp_dir": "/tmp/alc-batch-...",
    "total_bytes": 18342011,
    "rows": [
        {
            "row_id": "row-0",
            "filename": "gs_001.png",
            "staged_path": "/tmp/alc-batch-.../row-0.png",
            "form_values": {...},
            "errors": {},
            "queue_state": "draft",  # draft | queued | processing | complete | processing_error
            "result": None,          # verify_label payload when successful
            "system_error": None,    # {"code": "processing_error", "message": "..."} when unexpected failure occurs
        }
    ],
}
```

Recommended lifecycle rules:

- Expire workspaces after about 30 minutes of inactivity.
- Clean up the temp directory when the batch expires or is explicitly discarded.
- On every batch route access, opportunistically delete stale workspaces first.

### Visible Queue Progression

The queue should be visible and truthful:

- Before run: each row is `draft`.
- After `POST /batch/{batch_id}/run`: each row becomes `queued`.
- During `POST /batch/{batch_id}/process-next`: one row becomes `processing`.
- After a successful verifier call: that row becomes `complete`.
- After an unexpected processing failure: that row becomes `processing_error`.

Client-side JS should poll `process-next` until there are no queued rows left. This gives the reviewer a visibly advancing queue without a hidden background worker.

### Validation and Retry Model

The plan must separate staging errors from row-data errors:

- `POST /batch/session`
  - validates file presence, file count, per-file size, and total staged bytes
  - returns `422` for semantic issues such as no files or too many files
  - returns `413` for payload-size violations
- `POST /batch/{batch_id}/run`
  - validates expected data for the already-staged rows
  - returns `422` on row-data validation errors, but preserves the batch workspace so the user can fix fields and retry without re-uploading files

---

## Upload Limit Policy

Batch uploads need explicit limits beyond the single-label path:

- Per-file limit: `20 MB`
- Batch file-count limit: `10`
- Batch total-byte limit: `100 MB`

Implementation guidance:

- Use `Content-Length` as an early reject when present for `POST /batch/session`, but do not trust it as the only guard.
- During streaming/staging, track:
  - bytes written for the current file
  - cumulative bytes written for the whole batch
- If one file exceeds `20 MB`, stop staging and return `413`.
- If cumulative staged bytes exceed `100 MB`, stop staging and return `413`.
- Clean up any partially staged temp directory before returning an error.

These limits should be covered by explicit tests:

- one file larger than `20 MB`
- multiple valid files whose total staged bytes exceed `100 MB`
- more than `10` files selected

---

## Row Result and Error Model

Successful rows keep the existing verifier payload unchanged:

- `overall_verdict`
- `recommended_action`
- `processing_ms`
- `field_results`

Unexpected batch-processing failures should not masquerade as OCR unreadability. Instead, the row should look like:

```python
{
    "queue_state": "processing_error",
    "result": None,
    "system_error": {
        "code": "processing_error",
        "message": "Unexpected processing error for this label. Review manually.",
    },
}
```

`display_verdict` and `display_action` are **not** stored on the row. The template hardcodes the verdict chip for `queue_state == "processing_error"`, and `compute_summary` branches on `queue_state` directly. These are the single sources of truth for derived display state on error rows.

UI guidance for `processing_error` rows:

- Count them under the summary’s `needs_review` total so the batch still reaches a terminal state.
- Optionally show a separate `system_error_count` near the summary.
- Render a clear row-level warning such as `Verification did not complete for this label.`
- Do not render fake field-by-field mismatch or unreadable statuses when no verifier result exists.

---

## Planned File Changes

### New Files

- `docs/plans/2026-04-16-m3-batch-review-beta.md`
- `tests/test_batch_web.py`
- `app/templates/batch.html`
- `app/templates/_batch_summary.html`
- `app/templates/_batch_rows.html`
- `app/templates/_batch_row.html`
- `app/templates/_field_results.html`

### Likely Modified Files

- `app/main.py`
- `app/templates/index.html`
- `app/templates/_result_panel.html`
- `app/static/workbench.css`

### Optional Helper Modules

- `app/web_helpers.py`
  - normalize form values
  - validate one row of expected data
  - build the application dict passed to `verify_label`
  - compute batch summary counts
- `app/batch_store.py`
  - create and fetch batch workspaces
  - stage files safely
  - expire and clean up stale workspaces
  - update row queue state and system-error metadata

---

## Task 1: Extract Shared Single-Row Helpers

**Why first:** M3 should reuse the M2 validation and application-building logic instead of duplicating it across two route families.

**Files:**
- Modify: `app/main.py`
- Optional create: `app/web_helpers.py`
- Add/modify tests: `tests/test_web.py`

**Implementation notes:**

- Extract the single-label expected-data validation into a reusable helper such as `validate_expected_data(form_values) -> dict[str, str]`.
- Extract application payload construction into a helper such as `build_application_payload(form_values) -> dict[str, object]`.
- Keep the single-label endpoint behavior unchanged:
  - missing image still returns `422`
  - required field errors still return `422`
  - oversized upload still returns `413`

**Acceptance check:**

```bash
pytest tests/test_web.py -v
```

---

## Task 2: Add Batch Workspace Creation and Safe File Staging

**Files:**
- Modify: `app/main.py`
- Create optional helper: `app/batch_store.py`
- Create: `app/templates/batch.html`
- Modify: `app/templates/index.html`
- Modify: `app/static/workbench.css`
- Add tests: `tests/test_batch_web.py`

**Implementation notes:**

- Add `GET /batch`.
- Add `POST /batch/session` with:
  - file-presence validation
  - `<= 10` files validation
  - `20 MB` per-file streaming cap
  - `100 MB` total staged-byte cap
  - temp directory cleanup on failure
- Redirect successful staging to `GET /batch/{batch_id}`.
- Add lightweight navigation between `/` and `/batch`.

**Acceptance checks:**

```bash
pytest tests/test_batch_web.py::TestBatchSession::test_batch_page_renders -v
pytest tests/test_batch_web.py::TestBatchSession::test_too_many_files_returns_422 -v
pytest tests/test_batch_web.py::TestBatchSession::test_single_file_over_limit_returns_413 -v
pytest tests/test_batch_web.py::TestBatchSession::test_total_batch_bytes_over_limit_returns_413 -v
```

---

## Task 3: Build the Retry-Safe Batch Workspace Editor

**Files:**
- Modify: `app/templates/batch.html`
- Modify: `app/static/workbench.css`
- Modify: `app/main.py`
- Add tests: `tests/test_batch_web.py`

**Implementation notes:**

- `GET /batch/{batch_id}` should show one editor row per staged file.
- Each row should mirror the M2 expected-data fields and default `government_warning` to the standard warning text.
- Add per-row import toggles that reveal `country_of_origin` for that row only.
- `POST /batch/{batch_id}/run` should validate row data without requiring files in the request.
- On `422`, re-render the same workspace with row errors while preserving filenames and user-entered values.

**Acceptance checks:**

```bash
pytest tests/test_batch_web.py::TestBatchWorkspace::test_workspace_renders_staged_rows -v
pytest tests/test_batch_web.py::TestBatchWorkspace::test_run_validation_error_preserves_staged_files -v
```

---

## Task 4: Implement Visible Queue Stepping

**Files:**
- Modify: `app/main.py`
- Optional modify: `app/batch_store.py`
- Modify: `app/templates/batch.html`
- Create: `app/templates/_batch_summary.html`
- Create: `app/templates/_batch_rows.html`
- Create: `app/templates/_batch_row.html`
- Add tests: `tests/test_batch_web.py`

**Implementation notes:**

- `POST /batch/{batch_id}/run`
  - validates row data
  - marks all draft rows as `queued`
  - returns the workspace with the polling loop enabled
- `POST /batch/{batch_id}/process-next`
  - finds the next `queued` row
  - marks it `processing`
  - runs `verify_label` for that row
  - marks the row `complete` on success
  - marks the row `processing_error` on unexpected exception
  - recomputes summary data
  - returns updated batch-status markup or JSON

Client-side polling should stop automatically when no queued rows remain.

**Acceptance checks:**

```bash
pytest tests/test_batch_web.py::TestBatchQueue::test_process_next_handles_one_row_per_call -v
pytest tests/test_batch_web.py::TestBatchQueue::test_process_next_updates_rows_in_order -v
pytest tests/test_batch_web.py::TestBatchQueue::test_processing_error_does_not_abort_later_rows -v
```

---

## Task 5: Render Summary, Drill-Down, and Processing Errors Clearly

**Files:**
- Create: `app/templates/_field_results.html`
- Modify: `app/templates/_result_panel.html`
- Modify: `app/templates/_batch_summary.html`
- Modify: `app/templates/_batch_row.html`
- Modify: `app/static/workbench.css`
- Add tests: `tests/test_batch_web.py`

**Implementation notes:**

- Extract the reusable field-results loop from `_result_panel.html` into `_field_results.html`.
- Batch summary should show:
  - `match`
  - `mismatch`
  - `needs_review`
- Also show smaller secondary counts for:
  - `manual_review`
  - `request_better_image`
  - optional `system_error_count`
- Each batch row should render:
  - filename
  - queue-state chip
  - display verdict/action
  - per-row `processing_ms` when available
  - drill-down toggle
- Successful rows reuse `_field_results.html`.
- `processing_error` rows render a row-level warning instead of fake field results.

**Acceptance checks:**

```bash
pytest tests/test_batch_web.py::TestBatchRendering::test_summary_counts_render -v
pytest tests/test_batch_web.py::TestBatchRendering::test_completed_row_renders_field_details -v
pytest tests/test_batch_web.py::TestBatchRendering::test_processing_error_row_renders_system_warning -v
```

---

## Task 6: Regression Tests, Cleanup, and Manual QA

**Files:**
- Create: `tests/test_batch_web.py`
- Optional modify: `scripts/smoke_verify.py`
- Optional create: `scripts/smoke_batch_verify.py`

**Recommended automated tests**

### Batch session creation

- batch page renders heading and `up to 10 images` guidance
- missing files returns `422`
- more than `10` files returns `422`
- one file over `20 MB` returns `413`
- total staged bytes over `100 MB` returns `413`

### Batch workspace validation

- staged filenames appear on `GET /batch/{batch_id}`
- imported row without `country_of_origin` returns `422`
- validation errors preserve staged filenames and entered values

### Queue stepping

- one `process-next` call handles exactly one row
- rows advance in uploaded order
- mixed results produce correct summary counts
- unexpected exception becomes `processing_error`
- later rows still complete after a `processing_error`

### Regression guardrails

- existing `tests/test_web.py` still passes unchanged
- `python3 evals/run_golden_set.py` still passes unchanged

**Suggested command set:**

```bash
pytest tests/test_batch_web.py -v
pytest tests/test_web.py -v
python3 evals/run_golden_set.py
```

**Manual QA checklist**

- Browser: `/batch` loads and clearly advertises `up to 10 images`
- Browser: staging files redirects to a workspace showing the selected filenames
- Browser: row validation errors can be fixed without re-uploading files
- Browser: running a 3-row batch shows rows moving from `queued` to `processing` to `complete`
- Browser: one mismatch row shows the same field-level drill-down as the single-label flow
- Browser: one unreadable verifier result highlights `request better image`
- Browser: one forced processing failure renders a clear system warning, not an `unreadable` field breakdown
- Browser: navigate back to `/` and confirm the single-label flow still works

---

## Recommended Implementation Order

1. Extract shared row-validation and application-building helpers.
2. Add batch workspace creation and safe file staging.
3. Build the retry-safe row editor for staged files.
4. Implement visible queue stepping with `process-next`.
5. Render summary, row drill-down, and system-error states.
6. Finish tests, cleanup, and manual QA.

---

## Final Acceptance Criteria

- `/` and `POST /verify` still behave exactly as they did in M2.
- `/batch` stages up to `10` files safely and redirects into a batch workspace.
- Reviewers can fix row-data validation errors without re-uploading files.
- The queue is visibly sequential: rows progress through `queued`, `processing`, and terminal states on-screen.
- `POST /batch/{batch_id}/process-next` processes one row at a time and continues after a single-row failure.
- Batch summary counts are grouped by verdict and clearly highlight human-attention actions.
- Unexpected processing failures are shown as system errors, not misclassified as unreadable label content.
- Successful batch rows expose the same field-level reasoning model used by the single-label flow.
- Web tests pass and the verifier eval harness remains green.
