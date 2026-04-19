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
