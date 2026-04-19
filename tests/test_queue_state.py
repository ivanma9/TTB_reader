from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.queue_state import (
    QueueItem,
    QueueLoadError,
    QueueStatus,
    ReviewerAction,
    add_item,
    configure_persistence,
    get_item,
    list_items,
    load_from_disk,
    mark_complete,
    mark_in_review,
    reset_queue,
    save_to_disk,
    seed_queue,
)


@pytest.fixture(autouse=True)
def _reset():
    configure_persistence(None)
    reset_queue()
    seed_queue()
    yield
    configure_persistence(None)
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


def _sample_kwargs(item_id: str = "gs_007") -> dict:
    return dict(
        id=item_id,
        application_id="COLA-2026-0419-042",
        submitter="Acme Distillery LLC",
        submitted_at=datetime(2026, 4, 19, 14, 30),
        beverage_class="Distilled Spirits",
        origin_badge="Domestic",
        image_path=Path("evals/golden_set/fixtures/gs_007.png"),
        form_values={"brand_name": "ACME"},
    )


class TestAddItem:
    def test_add_item_appends_and_returns(self):
        reset_queue()
        item = add_item(**_sample_kwargs("gs_007"))
        assert item.id == "gs_007"
        assert item.status == QueueStatus.PENDING
        assert get_item("gs_007") is item
        assert len(list_items()) == 1

    def test_add_item_duplicate_id_raises(self):
        # autouse fixture already seeded gs_001
        with pytest.raises(ValueError, match="already in queue"):
            add_item(**_sample_kwargs("gs_001"))

    def test_add_item_preserves_supplied_fields(self):
        reset_queue()
        kwargs = _sample_kwargs("gs_007")
        item = add_item(**kwargs)
        assert item.application_id == kwargs["application_id"]
        assert item.submitter == kwargs["submitter"]
        assert item.submitted_at == kwargs["submitted_at"]
        assert item.origin_badge == "Domestic"
        assert item.image_path == kwargs["image_path"]
        assert item.form_values == kwargs["form_values"]


class TestPersistence:
    def test_save_writes_all_items(self, tmp_path):
        path = tmp_path / "queue.json"
        save_to_disk(path)
        data = json.loads(path.read_text())
        assert len(data["items"]) == 3
        ids = {it["id"] for it in data["items"]}
        assert ids == {"gs_001", "gs_003", "gs_020"}

    def test_roundtrip_preserves_status_and_verdict(self, tmp_path):
        path = tmp_path / "queue.json"
        mark_in_review("gs_001", {"overall_verdict": "match", "field_results": {}})
        save_to_disk(path)

        reset_queue()
        load_from_disk(path)
        item = get_item("gs_001")
        assert item is not None
        assert item.status == QueueStatus.IN_REVIEW
        assert item.verdict == {"overall_verdict": "match", "field_results": {}}

    def test_roundtrip_preserves_completed_action(self, tmp_path):
        path = tmp_path / "queue.json"
        mark_in_review("gs_001", {"overall_verdict": "match", "field_results": {}})
        mark_complete("gs_001", ReviewerAction.APPROVED)
        save_to_disk(path)

        reset_queue()
        load_from_disk(path)
        item = get_item("gs_001")
        assert item is not None
        assert item.status == QueueStatus.COMPLETE
        assert item.reviewer_action == ReviewerAction.APPROVED
        assert item.completed_at is not None

    def test_roundtrip_preserves_image_path_type(self, tmp_path):
        path = tmp_path / "queue.json"
        save_to_disk(path)
        reset_queue()
        load_from_disk(path)
        item = get_item("gs_001")
        assert isinstance(item.image_path, Path)

    def test_load_missing_file_is_noop(self, tmp_path):
        reset_queue()
        load_from_disk(tmp_path / "nope.json")
        assert list_items() == []

    def test_save_is_atomic_final_state(self, tmp_path):
        path = tmp_path / "queue.json"
        save_to_disk(path)
        mark_in_review("gs_001", {"overall_verdict": "match"})
        save_to_disk(path)
        data = json.loads(path.read_text())
        g001 = next(it for it in data["items"] if it["id"] == "gs_001")
        assert g001["status"] == "in_review"

    def test_save_leaves_no_tmp_sibling(self, tmp_path):
        path = tmp_path / "queue.json"
        save_to_disk(path)
        siblings = [p.name for p in tmp_path.iterdir()]
        assert "queue.json" in siblings
        assert not any(s.endswith(".json.tmp") for s in siblings)

    def test_load_malformed_json_raises_queue_load_error(self, tmp_path):
        path = tmp_path / "queue.json"
        path.write_text("{not json")
        with pytest.raises(QueueLoadError):
            load_from_disk(path)

    def test_load_wrong_top_level_shape_raises(self, tmp_path):
        path = tmp_path / "queue.json"
        path.write_text('["not", "an", "object"]')
        with pytest.raises(QueueLoadError):
            load_from_disk(path)

    def test_load_non_list_items_raises(self, tmp_path):
        path = tmp_path / "queue.json"
        path.write_text('{"items": {"gs_001": "nope"}}')
        with pytest.raises(QueueLoadError):
            load_from_disk(path)

    def test_load_preserves_memory_on_error(self, tmp_path):
        path = tmp_path / "queue.json"
        path.write_text("{garbage")
        before = {i.id for i in list_items()}
        with pytest.raises(QueueLoadError):
            load_from_disk(path)
        after = {i.id for i in list_items()}
        assert before == after


class TestAutosave:
    def test_add_item_autosaves(self, tmp_path):
        path = tmp_path / "queue.json"
        configure_persistence(path)
        add_item(**_sample_kwargs("gs_007"))
        # Fresh process sim: reset + reload
        configure_persistence(None)
        reset_queue()
        load_from_disk(path)
        assert get_item("gs_007") is not None

    def test_mark_in_review_autosaves(self, tmp_path):
        path = tmp_path / "queue.json"
        save_to_disk(path)  # seed on disk
        configure_persistence(path)
        mark_in_review("gs_001", {"overall_verdict": "match"})
        configure_persistence(None)
        reset_queue()
        load_from_disk(path)
        item = get_item("gs_001")
        assert item.status == QueueStatus.IN_REVIEW

    def test_mark_complete_autosaves(self, tmp_path):
        path = tmp_path / "queue.json"
        save_to_disk(path)
        configure_persistence(path)
        mark_in_review("gs_001", {"overall_verdict": "match"})
        mark_complete("gs_001", ReviewerAction.APPROVED)
        configure_persistence(None)
        reset_queue()
        load_from_disk(path)
        item = get_item("gs_001")
        assert item.status == QueueStatus.COMPLETE
        assert item.reviewer_action == ReviewerAction.APPROVED

    def test_no_autosave_when_unconfigured(self, tmp_path):
        path = tmp_path / "queue.json"
        configure_persistence(None)
        add_item(**_sample_kwargs("gs_007"))
        assert not path.exists()


class TestInitQueueState:
    def test_no_env_var_just_seeds(self, monkeypatch):
        from app.main import init_queue_state

        monkeypatch.delenv("QUEUE_PERSIST_PATH", raising=False)
        reset_queue()
        init_queue_state()
        ids = {item.id for item in list_items()}
        assert ids == {"gs_001", "gs_003", "gs_020"}

    def test_env_var_first_boot_seeds_and_writes(self, monkeypatch, tmp_path):
        from app.main import init_queue_state

        path = tmp_path / "queue.json"
        monkeypatch.setenv("QUEUE_PERSIST_PATH", str(path))
        reset_queue()
        init_queue_state()
        assert path.exists()
        assert len(list_items()) == 3

    def test_env_var_second_boot_loads_existing(self, monkeypatch, tmp_path):
        from app.main import init_queue_state

        path = tmp_path / "queue.json"
        monkeypatch.setenv("QUEUE_PERSIST_PATH", str(path))

        # "First boot" — seed + persist, then simulate a new item
        reset_queue()
        init_queue_state()
        add_item(**_sample_kwargs("gs_007"))

        # "Second boot" — fresh in-memory state, should reload from disk
        configure_persistence(None)
        reset_queue()
        init_queue_state()
        ids = {item.id for item in list_items()}
        assert ids == {"gs_001", "gs_003", "gs_020", "gs_007"}

    def test_malformed_persist_file_reseeds(self, monkeypatch, tmp_path):
        from app.main import init_queue_state

        path = tmp_path / "queue.json"
        path.write_text("{garbage")
        monkeypatch.setenv("QUEUE_PERSIST_PATH", str(path))
        configure_persistence(None)
        reset_queue()
        init_queue_state()
        ids = {item.id for item in list_items()}
        assert ids == {"gs_001", "gs_003", "gs_020"}
        # And the bad file should have been overwritten with a valid one
        assert path.read_text().startswith("{")
