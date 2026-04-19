from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.queue_state import (
    add_item,
    get_item,
    list_items,
    reset_queue,
    seed_queue,
)
from app.simulation_pool import POOL_CASES


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


def _fill_queue_from_pool(exclude: set[str] | None = None) -> None:
    """Force-populate the queue with every pool case (minus `exclude`). Test helper."""
    exclude = exclude or set()
    for case_id, case in POOL_CASES.items():
        if case_id in exclude:
            continue
        add_item(
            id=case_id,
            application_id=f"COLA-2026-0419-{case_id[-3:]}",
            submitter="Test Submitter",
            submitted_at=datetime(2026, 4, 19, 12, 0),
            beverage_class="Distilled Spirits",
            origin_badge="Import" if case.is_import else "Domestic",
            image_path=case.image_path,
            form_values=case.form_values,
        )


class TestQueueLandingSimulateButton:
    def test_landing_shows_simulate_button(self, client):
        r = client.get("/")
        assert 'action="/queue/simulate"' in r.text
        assert "Simulate submission" in r.text

    def test_button_not_disabled_by_default(self, client):
        r = client.get("/")
        # Grab the button opening tag; it should not have a disabled attribute
        import re as _re
        m = _re.search(r'<button[^>]*Simulate submission', r.text)
        # Fallback: find the button tag anywhere
        button_tag = _re.search(r'<button[^>]*>\s*\+?\s*Simulate submission', r.text)
        assert button_tag, "could not find simulate button in rendered HTML"
        assert "disabled" not in button_tag.group(0)

    def test_button_disabled_when_pool_exhausted(self, client):
        reset_queue()
        _fill_queue_from_pool()
        r = client.get("/")
        import re as _re
        button_tag = _re.search(r'<button[^>]*>\s*\+?\s*Simulate submission', r.text)
        assert button_tag, "could not find simulate button in rendered HTML"
        assert "disabled" in button_tag.group(0)
        assert "All demo cases" in r.text  # tooltip


class TestQueueSimulate:
    def test_simulate_adds_item_and_redirects(self, client):
        r = client.post("/queue/simulate", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        # 3 seeded + 1 new
        assert len(list_items()) == 4

    def test_simulate_new_item_visible_on_landing(self, client):
        client.post("/queue/simulate")
        r = client.get("/")
        seeded = {"COLA-2026-0412-001", "COLA-2026-0413-027", "COLA-2026-0415-009"}
        found = set(re.findall(r"COLA-\d{4}-\d{4}-\d{3}", r.text))
        assert found - seeded, f"expected a non-seeded COLA id on landing; found={found}"

    def test_simulate_when_exhausted_returns_409(self, client):
        reset_queue()
        _fill_queue_from_pool()
        r = client.post("/queue/simulate")
        assert r.status_code == 409

    def test_simulate_picks_case_not_already_queued(self, client):
        reset_queue()
        missing = "gs_014"
        _fill_queue_from_pool(exclude={missing})
        r = client.post("/queue/simulate", follow_redirects=False)
        assert r.status_code == 303
        assert get_item(missing) is not None

    def test_simulate_sets_submitter_and_origin(self, client):
        reset_queue()
        missing = "gs_003"  # import (Sierra Azul)
        _fill_queue_from_pool(exclude={missing})
        client.post("/queue/simulate", follow_redirects=False)
        item = get_item(missing)
        assert item is not None
        assert item.origin_badge == "Import"
        assert item.submitter == "Sierra Azul Imports"
        assert item.beverage_class == "Distilled Spirits"
        # COLA id shape
        assert re.fullmatch(r"COLA-\d{4}-\d{4}-\d{3}", item.application_id)

    def test_simulate_fills_image_path_and_form_values(self, client):
        reset_queue()
        missing = "gs_007"  # domestic, Stone's Throw
        _fill_queue_from_pool(exclude={missing})
        client.post("/queue/simulate", follow_redirects=False)
        item = get_item(missing)
        assert item is not None
        assert isinstance(item.image_path, Path)
        assert item.image_path.exists()
        assert item.form_values["brand_name"] == "Stone's Throw"
        assert item.submitter == "Stone's Throw LLC"


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
