"""Curated demo cases for the reviewer landing page.

Each entry points at a golden-set fixture image plus the matching application
payload, so a reviewer can one-click through the single-label flow without
having to upload a file or fill in the seven tracked fields by hand.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict


class DemoCase(TypedDict):
    case_id: str
    label: str
    blurb: str
    expected_verdict: str
    image_path: Path
    form_values: dict[str, str | None]


_FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "golden_set" / "fixtures"

_STANDARD_WARNING = (
    "GOVERNMENT WARNING: According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. Consumption of alcoholic beverages impairs your ability to drive "
    "a car or operate machinery, and may cause health problems."
)


DEMO_CASES: dict[str, DemoCase] = {
    "gs_001": {
        "case_id": "gs_001",
        "label": "Clean domestic match",
        "blurb": "Standard domestic bourbon — every field matches the application.",
        "expected_verdict": "match",
        "image_path": _FIXTURES / "gs_001.png",
        "form_values": {
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "producer_name_address": "Old Tom Distillery, Louisville, KY",
            "is_import": None,
            "country_of_origin": "",
            "government_warning": _STANDARD_WARNING,
        },
    },
    "gs_003": {
        "case_id": "gs_003",
        "label": "Import with country of origin",
        "blurb": "Imported tequila with the correct country of origin — exercises the conditional rule.",
        "expected_verdict": "match",
        "image_path": _FIXTURES / "gs_003.png",
        "form_values": {
            "brand_name": "SIERRA AZUL",
            "class_type": "Reposado Tequila",
            "alcohol_content": "40% Alc./Vol. (80 Proof)",
            "net_contents": "750 mL",
            "producer_name_address": "Sierra Azul Imports, Austin, TX",
            "is_import": "1",
            "country_of_origin": "Mexico",
            "government_warning": _STANDARD_WARNING,
        },
    },
    "gs_020": {
        "case_id": "gs_020",
        "label": "Needs review (occluded warning)",
        "blurb": "Government warning is partially occluded — the verifier should request a better image.",
        "expected_verdict": "needs_review",
        "image_path": _FIXTURES / "gs_020.png",
        "form_values": {
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "producer_name_address": "Old Tom Distillery, Louisville, KY",
            "is_import": None,
            "country_of_origin": "",
            "government_warning": _STANDARD_WARNING,
        },
    },
}


def get_demo_case(case_id: str) -> DemoCase | None:
    return DEMO_CASES.get(case_id)
