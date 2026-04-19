"""Pool of golden-set cases used by the 'Simulate submission' demo affordance.

Loads `evals/golden_set/cases.jsonl` at import time and translates each
application payload into the web form_values shape used by the queue
(is_import as "1" or None, country_of_origin as str or "").
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CASES_JSONL = _REPO_ROOT / "evals" / "golden_set" / "cases.jsonl"


@dataclass(frozen=True)
class PoolCase:
    case_id: str
    brand_name: str
    is_import: bool
    image_path: Path
    form_values: dict[str, str | None]


def _titlecase_brand(brand: str) -> str:
    """Titlecase only if the brand is shouted in all-caps; otherwise preserve.

    `.title()` mangles possessives (e.g. "Stone's Throw" → "Stone'S Throw"),
    so we only apply it when the caller clearly intended a display cast-up.
    """
    if brand.isupper():
        return brand.title()
    return brand


def _application_to_form_values(app: dict) -> dict[str, str | None]:
    is_import = bool(app.get("is_import"))
    country = app.get("country_of_origin")
    return {
        "brand_name": app.get("brand_name", ""),
        "class_type": app.get("class_type", ""),
        "alcohol_content": app.get("alcohol_content", ""),
        "net_contents": app.get("net_contents", ""),
        "producer_name_address": app.get("producer_name_address", ""),
        "is_import": "1" if is_import else None,
        "country_of_origin": country if (is_import and country) else "",
        "government_warning": app.get("government_warning", ""),
    }


def _load_pool() -> dict[str, PoolCase]:
    """Parse cases.jsonl into PoolCase records.

    On any I/O or parse error logs a warning and returns an empty dict so the
    app boots cleanly — the simulate endpoint naturally returns 409 and the
    Phase 3 button renders as disabled. Do not let eval-only data brick prod.
    """
    try:
        text = _CASES_JSONL.read_text()
    except OSError as exc:
        log.warning("simulation pool disabled — cases.jsonl unreadable: %s", exc)
        return {}

    cases: dict[str, PoolCase] = {}
    try:
        for line in text.splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            inputs = rec["inputs"]
            app = inputs["application"]
            case_id = inputs["case_id"]
            cases[case_id] = PoolCase(
                case_id=case_id,
                brand_name=app["brand_name"],
                is_import=bool(app.get("is_import")),
                image_path=_REPO_ROOT / inputs["label_image_path"],
                form_values=_application_to_form_values(app),
            )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.warning("simulation pool disabled — cases.jsonl malformed: %s", exc)
        return {}
    return cases


POOL_CASES: dict[str, PoolCase] = _load_pool()


def pick_unqueued_case(queued_case_ids: set[str]) -> PoolCase | None:
    remaining = [c for cid, c in POOL_CASES.items() if cid not in queued_case_ids]
    if not remaining:
        return None
    return random.choice(remaining)


def derive_submitter(case: PoolCase) -> str:
    display = _titlecase_brand(case.brand_name)
    suffix = " Imports" if case.is_import else " LLC"
    return display + suffix
