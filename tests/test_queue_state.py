from __future__ import annotations

import pytest

from app.queue_state import (
    QueueItem,
    QueueStatus,
    ReviewerAction,
    get_item,
    list_items,
    mark_complete,
    mark_in_review,
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
