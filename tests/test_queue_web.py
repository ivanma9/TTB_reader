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
        assert "Old Tom Distillery" in r.text
        assert "Sierra Azul Imports" in r.text

    def test_landing_shows_pending_badges(self, client):
        r = client.get("/")
        assert r.text.count("Pending") >= 3

    def test_landing_shows_application_ids(self, client):
        r = client.get("/")
        assert "COLA-2026-0412-001" in r.text

    def test_landing_links_to_items(self, client):
        r = client.get("/")
        assert '/queue/gs_001' in r.text
        assert '/queue/gs_003' in r.text
        assert '/queue/gs_020' in r.text


class TestQueueItemDetail:
    def test_renders_application_fields_readonly(self, client):
        r = client.get("/queue/gs_001")
        assert r.status_code == 200
        assert "OLD TOM DISTILLERY" in r.text
        assert "Kentucky Straight Bourbon Whiskey" in r.text
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


class TestQueueItemVerify:
    def test_verify_runs_and_transitions_to_in_review(self, client):
        stub = {
            "overall_verdict": "match",
            "recommended_action": "accept",
            "field_results": {},
            "processing_ms": 123,
        }
        with patch("app.main.verify_label", return_value=stub):
            r = client.post("/queue/gs_001/verify")
        assert r.status_code == 200
        assert "Verification result" in r.text
        assert 'value="approved"' in r.text
        assert 'value="rejected"' in r.text

    def test_verify_unknown_id_404(self, client):
        r = client.post("/queue/nope/verify")
        assert r.status_code == 404


class TestQueueItemAction:
    def test_action_marks_complete_and_redirects(self, client):
        stub = {"overall_verdict": "match", "recommended_action": "accept", "field_results": {}}
        with patch("app.main.verify_label", return_value=stub):
            client.post("/queue/gs_001/verify")

        r = client.post("/queue/gs_001/action", data={"action": "approved"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"

        r = client.get("/")
        assert "Complete · Approved" in r.text

    def test_action_rejected_shows_on_queue(self, client):
        stub = {"overall_verdict": "mismatch", "recommended_action": "manual_review", "field_results": {}}
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

    def test_action_rejected_when_not_in_review(self, client):
        r = client.post(
            "/queue/gs_020/action",
            data={"action": "approved"},
            follow_redirects=False,
        )
        assert r.status_code == 409


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
