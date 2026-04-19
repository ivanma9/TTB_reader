"""In-memory queue of pre-paired application+label records for the reviewer."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
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
_PERSIST_PATH: Optional[Path] = None


def configure_persistence(path: Optional[Path]) -> None:
    global _PERSIST_PATH
    _PERSIST_PATH = Path(path) if path is not None else None


def _autosave() -> None:
    if _PERSIST_PATH is not None:
        save_to_disk(_PERSIST_PATH)


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
        "submitted_at": datetime(2026, 4, 13, 14, 2),
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


def add_item(
    *,
    id: str,
    application_id: str,
    submitter: str,
    submitted_at: datetime,
    beverage_class: str,
    origin_badge: str,
    image_path: Path,
    form_values: dict[str, str | None],
) -> QueueItem:
    if id in _QUEUE:
        raise ValueError(f"{id!r} already in queue")
    item = QueueItem(
        id=id,
        submitter=submitter,
        application_id=application_id,
        submitted_at=submitted_at,
        beverage_class=beverage_class,
        origin_badge=origin_badge,
        image_path=image_path,
        form_values=dict(form_values),
    )
    _QUEUE[id] = item
    _autosave()
    return item


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
    _autosave()
    return item


def mark_complete(item_id: str, action: ReviewerAction) -> Optional[QueueItem]:
    item = _QUEUE.get(item_id)
    if item is None:
        return None
    item.status = QueueStatus.COMPLETE
    item.reviewer_action = action
    item.completed_at = datetime.now()
    _autosave()
    return item


def _serialize_item(item: QueueItem) -> dict:
    return {
        "id": item.id,
        "submitter": item.submitter,
        "application_id": item.application_id,
        "submitted_at": item.submitted_at.isoformat(),
        "beverage_class": item.beverage_class,
        "origin_badge": item.origin_badge,
        "image_path": str(item.image_path),
        "form_values": item.form_values,
        "status": item.status.value,
        "verdict": item.verdict,
        "reviewer_action": item.reviewer_action.value if item.reviewer_action else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def _deserialize_item(raw: dict) -> QueueItem:
    return QueueItem(
        id=raw["id"],
        submitter=raw["submitter"],
        application_id=raw["application_id"],
        submitted_at=datetime.fromisoformat(raw["submitted_at"]),
        beverage_class=raw["beverage_class"],
        origin_badge=raw["origin_badge"],
        image_path=Path(raw["image_path"]),
        form_values=raw["form_values"],
        status=QueueStatus(raw["status"]),
        verdict=raw.get("verdict"),
        reviewer_action=(
            ReviewerAction(raw["reviewer_action"]) if raw.get("reviewer_action") else None
        ),
        completed_at=(
            datetime.fromisoformat(raw["completed_at"]) if raw.get("completed_at") else None
        ),
    )


def save_to_disk(path: Path) -> None:
    path = Path(path)
    payload = {"items": [_serialize_item(item) for item in _QUEUE.values()]}
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)


def load_from_disk(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        return
    data = json.loads(path.read_text())
    _QUEUE.clear()
    for raw in data.get("items", []):
        item = _deserialize_item(raw)
        _QUEUE[item.id] = item
