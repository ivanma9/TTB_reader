"""Web layer tests for the /test manual-entry surface."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
GS_001 = ROOT / "evals" / "golden_set" / "fixtures" / "gs_001.png"

STANDARD_WARNING = (
    "GOVERNMENT WARNING: According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. Consumption of alcoholic beverages impairs your ability to drive "
    "a car or operate machinery, and may cause health problems."
)

VALID_FORM = {
    "brand_name": "Old Tom",
    "class_type": "Distilled Spirits",
    "alcohol_content": "40% Alc./Vol. (80 Proof)",
    "net_contents": "750 mL",
    "producer_name_address": "Test Distillery, Springfield, USA",
    "government_warning": STANDARD_WARNING,
}


def make_client() -> TestClient:
    with patch("app.main.warm_ocr"):
        from app.main import app
        return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def client():
    return make_client()


# ── healthz ──────────────────────────────────────────────────────────────────

class TestHealthz:
    def test_healthz_ok(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ── GET /test ────────────────────────────────────────────────────────────────

class TestTestSurfacePage:
    def test_test_renders_workbench(self, client):
        r = client.get("/test")
        assert r.status_code == 200
        assert "Test a label" in r.text

    def test_test_has_import_toggle(self, client):
        r = client.get("/test")
        assert "is_import" in r.text

    def test_test_has_warning_prefilled(self, client):
        r = client.get("/test")
        assert "GOVERNMENT WARNING:" in r.text

    def test_test_empty_results_state(self, client):
        r = client.get("/test")
        assert "Results will appear here after verification." in r.text


# ── POST /test/verify — validation errors ────────────────────────────────────

class TestFormValidation:
    def test_missing_image_returns_422(self, client):
        r = client.post("/test/verify", data=VALID_FORM)
        assert r.status_code == 422
        assert "Label image is required" in r.text

    def test_missing_brand_name_returns_error(self, client):
        bad = {**VALID_FORM, "brand_name": ""}
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        r = client.post(
            "/test/verify",
            data=bad,
            files={"label_image": ("test.png", image_bytes, "image/png")},
        )
        assert r.status_code == 422
        assert "brand_name" in r.text or "Required" in r.text

    def test_import_without_country_returns_error(self, client):
        form = {**VALID_FORM, "is_import": "1", "country_of_origin": ""}
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        r = client.post(
            "/test/verify",
            data=form,
            files={"label_image": ("test.png", image_bytes, "image/png")},
        )
        assert r.status_code == 422
        assert "country_of_origin" in r.text or "Required" in r.text

    def test_oversized_upload_returns_413(self, client):
        large = b"\x00" * (21 * 1024 * 1024)
        r = client.post(
            "/test/verify",
            data=VALID_FORM,
            files={"label_image": ("big.png", large, "image/png")},
        )
        assert r.status_code == 413

    def test_verifier_not_called_on_validation_failure(self, client):
        with patch("app.main.verify_label") as mock_verify:
            client.post("/test/verify", data=VALID_FORM)
            mock_verify.assert_not_called()


# ── POST /test/verify — verifier integration (mocked) ────────────────────────

def _mock_match_result():
    return {
        "overall_verdict": "match",
        "recommended_action": "accept",
        "processing_ms": 123,
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


def _mock_mismatch_result():
    return {
        "overall_verdict": "mismatch",
        "recommended_action": "manual_review",
        "processing_ms": 200,
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


def _mock_unreadable_result():
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


class TestVerifyEndpoint:
    def _post_valid(self, client, extra_data=None, image_bytes=None):
        data = {**VALID_FORM, **(extra_data or {})}
        img = image_bytes or (b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        return client.post(
            "/test/verify",
            data=data,
            files={"label_image": ("label.png", img, "image/png")},
        )

    def test_match_result_renders_accept(self, client):
        with patch("app.main.verify_label", return_value=_mock_match_result()):
            r = self._post_valid(client)
        assert r.status_code == 200
        assert "Match" in r.text or "Accept" in r.text.lower() or "accept" in r.text

    def test_mismatch_renders_manual_review(self, client):
        with patch("app.main.verify_label", return_value=_mock_mismatch_result()):
            r = self._post_valid(client)
        assert r.status_code == 200
        assert "Mismatch" in r.text

    def test_mismatch_shows_observed_value(self, client):
        with patch("app.main.verify_label", return_value=_mock_mismatch_result()):
            r = self._post_valid(client)
        assert "WRONG BRAND" in r.text

    def test_unreadable_renders_needs_review(self, client):
        with patch("app.main.verify_label", return_value=_mock_unreadable_result()):
            r = self._post_valid(client)
        assert r.status_code == 200
        assert "Needs Review" in r.text or "needs_review" in r.text.lower()

    def test_unreadable_image_bytes_shows_needs_review(self, client):
        with patch("app.main.verify_label", return_value=_mock_unreadable_result()):
            r = self._post_valid(client)
        assert r.status_code == 200
        assert "Needs Review" in r.text or "needs_review" in r.text.lower()

    def test_unexpected_verifier_exception_returns_500(self, client):
        from app.main import app as _app
        client2 = TestClient(_app, raise_server_exceptions=False)
        with patch("app.main.verify_label", side_effect=RuntimeError("boom")):
            r = client2.post(
                "/test/verify",
                data=VALID_FORM,
                files={"label_image": ("label.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "image/png")},
            )
        assert r.status_code == 500

    def test_processing_ms_shown(self, client):
        with patch("app.main.verify_label", return_value=_mock_match_result()):
            r = self._post_valid(client)
        assert "Processed in 123" in r.text or "123 ms" in r.text
