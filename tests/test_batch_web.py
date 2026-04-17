"""Web layer tests for the M3 batch review flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

STANDARD_WARNING = (
    "GOVERNMENT WARNING: According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. Consumption of alcoholic beverages impairs your ability to drive "
    "a car or operate machinery, and may cause health problems."
)

VALID_ROW = {
    "brand_name": "Old Tom",
    "class_type": "Distilled Spirits",
    "alcohol_content": "40% Alc./Vol. (80 Proof)",
    "net_contents": "750 mL",
    "producer_name_address": "Test Distillery, Springfield, USA",
    "government_warning": STANDARD_WARNING,
}

_TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def make_client() -> TestClient:
    with patch("app.main.warm_ocr"):
        from app.main import app
        return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def client():
    return make_client()


def _upload_one(client: TestClient, image_bytes: bytes = _TINY_PNG, filename: str = "label.png"):
    """Helper: POST /batch/session with a single file; follow redirect to workspace."""
    r = client.post(
        "/batch/session",
        files={"label_images": (filename, image_bytes, "image/png")},
        follow_redirects=True,
    )
    return r


def _stage_batch(client: TestClient, n: int = 1, image_bytes: bytes = _TINY_PNG):
    """Stage n files and return the batch_id from the redirect URL."""
    files = [("label_images", (f"label_{i}.png", image_bytes, "image/png")) for i in range(n)]
    r = client.post("/batch/session", files=files, follow_redirects=False)
    assert r.status_code == 303, f"Expected 303, got {r.status_code}: {r.text[:200]}"
    location = r.headers["location"]
    batch_id = location.split("/batch/")[1]
    return batch_id


def _make_run_data(batch_id: str, rows_data: list[dict]) -> dict:
    """Build form data dict for POST /batch/{batch_id}/run."""
    from app.batch_store import get_workspace
    workspace = get_workspace(batch_id)
    assert workspace is not None
    form: dict = {}
    for i, row in enumerate(workspace["rows"]):
        rid = row["row_id"]
        values = rows_data[i] if i < len(rows_data) else {}
        for field, val in values.items():
            form[f"{rid}__{field}"] = val
    return form


def _mock_match():
    return {
        "overall_verdict": "match",
        "recommended_action": "accept",
        "processing_ms": 100,
        "field_results": {
            "brand_name": {"status": "match", "reason_code": "exact_match"},
            "class_type": {"status": "match", "reason_code": "normalized_match"},
            "alcohol_content": {"status": "match", "reason_code": "normalized_match"},
            "net_contents": {"status": "match", "reason_code": "normalized_match"},
            "producer_name_address": {"status": "match", "reason_code": "normalized_match"},
            "country_of_origin": {"status": "not_applicable", "reason_code": "not_applicable"},
            "government_warning": {"status": "match", "reason_code": "exact_match"},
        },
    }


def _mock_mismatch():
    return {
        "overall_verdict": "mismatch",
        "recommended_action": "manual_review",
        "processing_ms": 150,
        "field_results": {
            "brand_name": {"status": "mismatch", "reason_code": "wrong_value",
                           "observed_value": "WRONG BRAND"},
            "class_type": {"status": "match", "reason_code": "normalized_match"},
            "alcohol_content": {"status": "match", "reason_code": "normalized_match"},
            "net_contents": {"status": "match", "reason_code": "normalized_match"},
            "producer_name_address": {"status": "match", "reason_code": "normalized_match"},
            "country_of_origin": {"status": "not_applicable", "reason_code": "not_applicable"},
            "government_warning": {"status": "match", "reason_code": "exact_match"},
        },
    }


def _mock_needs_review():
    return {
        "overall_verdict": "needs_review",
        "recommended_action": "request_better_image",
        "processing_ms": 50,
        "field_results": {
            name: {"status": "needs_review", "reason_code": "unreadable"}
            for name in [
                "brand_name", "class_type", "alcohol_content", "net_contents",
                "producer_name_address", "country_of_origin", "government_warning",
            ]
        },
    }


# ── GET /batch ────────────────────────────────────────────────────────────────

class TestBatchPage:
    def test_batch_page_renders(self, client):
        r = client.get("/batch")
        assert r.status_code == 200
        assert "Batch Review" in r.text

    def test_batch_page_shows_10_image_guidance(self, client):
        r = client.get("/batch")
        assert r.status_code == 200
        assert "10" in r.text and "image" in r.text.lower()

    def test_batch_page_has_nav_link_to_single(self, client):
        r = client.get("/batch")
        assert "Single Label" in r.text or 'href="/"' in r.text


# ── POST /batch/session ───────────────────────────────────────────────────────

class TestBatchSession:
    def test_batch_page_renders(self, client):
        r = client.get("/batch")
        assert r.status_code == 200
        assert "Batch Review" in r.text

    def test_missing_files_returns_422(self, client):
        r = client.post("/batch/session", data={})
        assert r.status_code == 422

    def test_too_many_files_returns_422(self, client):
        files = [("label_images", (f"f{i}.png", _TINY_PNG, "image/png")) for i in range(11)]
        r = client.post("/batch/session", files=files)
        assert r.status_code == 422

    def test_single_file_over_limit_returns_413(self, client):
        big = b"\x00" * (21 * 1024 * 1024)
        r = client.post(
            "/batch/session",
            files={"label_images": ("big.png", big, "image/png")},
        )
        assert r.status_code == 413

    def test_total_batch_bytes_over_limit_returns_413(self, client):
        # Two files each 51 MB → 102 MB total > 100 MB
        large = b"\x00" * (51 * 1024 * 1024)
        files = [
            ("label_images", ("a.png", large, "image/png")),
            ("label_images", ("b.png", large, "image/png")),
        ]
        r = client.post("/batch/session", files=files)
        assert r.status_code == 413

    def test_valid_upload_redirects_to_workspace(self, client):
        r = client.post(
            "/batch/session",
            files={"label_images": ("label.png", _TINY_PNG, "image/png")},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/batch/b_" in r.headers["location"]

    def test_valid_upload_workspace_renders(self, client):
        r = _upload_one(client)
        assert r.status_code == 200
        assert "label.png" in r.text


# ── GET /batch/{batch_id} ─────────────────────────────────────────────────────

class TestBatchWorkspace:
    def test_workspace_renders_staged_rows(self, client):
        files = [
            ("label_images", ("gs_001.png", _TINY_PNG, "image/png")),
            ("label_images", ("gs_002.png", _TINY_PNG, "image/png")),
        ]
        r = client.post("/batch/session", files=files, follow_redirects=True)
        assert r.status_code == 200
        assert "gs_001.png" in r.text
        assert "gs_002.png" in r.text

    def test_workspace_404_for_unknown_batch(self, client):
        r = client.get("/batch/b_doesnotexist")
        assert r.status_code == 404

    def test_workspace_defaults_government_warning(self, client):
        r = _upload_one(client)
        assert "GOVERNMENT WARNING:" in r.text

    def test_run_validation_error_preserves_staged_files(self, client):
        batch_id = _stage_batch(client, n=1)
        # Submit with missing brand_name
        r = client.post(
            f"/batch/{batch_id}/run",
            data={f"row-0__brand_name": ""},
            follow_redirects=False,
        )
        assert r.status_code == 422
        assert "label_0.png" in r.text or "label.png" in r.text or "label_0" in r.text

    def test_run_validation_error_shows_field_errors(self, client):
        batch_id = _stage_batch(client, n=1)
        r = client.post(
            f"/batch/{batch_id}/run",
            data={},
            follow_redirects=False,
        )
        assert r.status_code == 422
        # Required error shown in the page
        assert "Required" in r.text

    def test_imported_row_without_country_returns_422(self, client):
        batch_id = _stage_batch(client, n=1)
        row_data = {**VALID_ROW, "is_import": "1", "country_of_origin": ""}
        form_data = _make_run_data(batch_id, [row_data])
        r = client.post(f"/batch/{batch_id}/run", data=form_data)
        assert r.status_code == 422
        assert "country_of_origin" in r.text or "Required" in r.text


# ── Queue stepping ────────────────────────────────────────────────────────────

class TestBatchQueue:
    def _stage_and_run(self, client, n: int = 1) -> str:
        batch_id = _stage_batch(client, n=n)
        form_data = _make_run_data(batch_id, [VALID_ROW] * n)
        r = client.post(f"/batch/{batch_id}/run", data=form_data)
        assert r.status_code == 200, f"Run failed: {r.text[:300]}"
        return batch_id

    def test_process_next_handles_one_row_per_call(self, client):
        batch_id = self._stage_and_run(client, n=3)

        with patch("app.main.verify_label", return_value=_mock_match()):
            r1 = client.post(f"/batch/{batch_id}/process-next")
        assert r1.status_code == 200
        data1 = r1.json()
        # Exactly one row should be complete after first call
        complete_rows = [r for r in data1["rows"] if r["queue_state"] == "complete"]
        assert len(complete_rows) == 1
        assert data1["done"] is False

    def test_process_next_updates_rows_in_order(self, client):
        batch_id = self._stage_and_run(client, n=3)

        results = [_mock_match(), _mock_mismatch(), _mock_needs_review()]
        completed_order = []
        for mock_result in results:
            with patch("app.main.verify_label", return_value=mock_result):
                r = client.post(f"/batch/{batch_id}/process-next")
            data = r.json()
            completed = [row for row in data["rows"] if row["queue_state"] == "complete"]
            completed_order.append(len(completed))

        assert completed_order == [1, 2, 3]

    def test_process_next_done_when_all_complete(self, client):
        batch_id = self._stage_and_run(client, n=1)

        with patch("app.main.verify_label", return_value=_mock_match()):
            r = client.post(f"/batch/{batch_id}/process-next")
        assert r.json()["done"] is True

    def test_processing_error_does_not_abort_later_rows(self, client):
        batch_id = self._stage_and_run(client, n=3)

        # First row raises an unexpected error
        with patch("app.main.verify_label", side_effect=RuntimeError("boom")):
            r1 = client.post(f"/batch/{batch_id}/process-next")
        data1 = r1.json()
        error_rows = [r for r in data1["rows"] if r["queue_state"] == "processing_error"]
        assert len(error_rows) == 1

        # Second and third rows still process normally
        with patch("app.main.verify_label", return_value=_mock_match()):
            r2 = client.post(f"/batch/{batch_id}/process-next")
            r3 = client.post(f"/batch/{batch_id}/process-next")

        data3 = r3.json()
        assert data3["done"] is True
        complete = [r for r in data3["rows"] if r["queue_state"] == "complete"]
        assert len(complete) == 2

    def test_process_next_404_for_unknown_batch(self, client):
        r = client.post("/batch/b_unknown123/process-next")
        assert r.status_code == 404

    def test_process_next_returns_done_when_no_queued_rows(self, client):
        batch_id = self._stage_and_run(client, n=1)
        with patch("app.main.verify_label", return_value=_mock_match()):
            client.post(f"/batch/{batch_id}/process-next")
        # Calling again when already done returns done=True
        r = client.post(f"/batch/{batch_id}/process-next")
        assert r.json()["done"] is True


# ── Rendering ─────────────────────────────────────────────────────────────────

class TestBatchRendering:
    def _run_full_batch(self, client, mock_results: list):
        n = len(mock_results)
        batch_id = _stage_batch(client, n=n)
        form_data = _make_run_data(batch_id, [VALID_ROW] * n)
        r = client.post(f"/batch/{batch_id}/run", data=form_data)
        assert r.status_code == 200

        for mock_result in mock_results:
            with patch("app.main.verify_label", return_value=mock_result):
                client.post(f"/batch/{batch_id}/process-next")
        return batch_id

    def test_summary_counts_render(self, client):
        batch_id = self._run_full_batch(
            client, [_mock_match(), _mock_mismatch(), _mock_needs_review()]
        )
        r = client.get(f"/batch/{batch_id}")
        assert r.status_code == 200
        assert "summary-match" in r.text or "Match" in r.text

    def test_completed_row_renders_field_details(self, client):
        batch_id = self._run_full_batch(client, [_mock_mismatch()])
        r = client.get(f"/batch/{batch_id}")
        assert r.status_code == 200
        assert "WRONG BRAND" in r.text

    def test_processing_error_row_renders_system_warning(self, client):
        n = 1
        batch_id = _stage_batch(client, n=n)
        form_data = _make_run_data(batch_id, [VALID_ROW])
        client.post(f"/batch/{batch_id}/run", data=form_data)

        with patch("app.main.verify_label", side_effect=RuntimeError("forced error")):
            client.post(f"/batch/{batch_id}/process-next")

        r = client.get(f"/batch/{batch_id}")
        assert r.status_code == 200
        assert "Verification did not complete" in r.text

    def test_processing_error_does_not_show_fake_field_results(self, client):
        n = 1
        batch_id = _stage_batch(client, n=n)
        form_data = _make_run_data(batch_id, [VALID_ROW])
        client.post(f"/batch/{batch_id}/run", data=form_data)

        with patch("app.main.verify_label", side_effect=RuntimeError("forced error")):
            client.post(f"/batch/{batch_id}/process-next")

        r = client.get(f"/batch/{batch_id}")
        # The error row should not contain fabricated "unreadable" field-level content
        # There should be no field_results drill-down for a processing_error row
        assert "brow-field-results" not in r.text or "Field details" not in r.text

    def test_mixed_results_summary_counts(self, client):
        batch_id = self._run_full_batch(
            client, [_mock_match(), _mock_mismatch(), _mock_needs_review()]
        )
        r = client.post(f"/batch/{batch_id}/process-next")
        data = r.json()
        summary = data["summary"]
        # After all rows done: 1 match + 1 mismatch + 1 needs_review
        assert summary["match"] == 1
        assert summary["mismatch"] == 1
        assert summary["needs_review"] == 1
