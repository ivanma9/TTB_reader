"""In-memory queue of pre-paired application+label records for the reviewer."""

from __future__ import annotations

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
    return item


def mark_complete(item_id: str, action: ReviewerAction) -> Optional[QueueItem]:
    item = _QUEUE.get(item_id)
    if item is None:
        return None
    item.status = QueueStatus.COMPLETE
    item.reviewer_action = action
    item.completed_at = datetime.now()
    return item
