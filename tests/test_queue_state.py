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
