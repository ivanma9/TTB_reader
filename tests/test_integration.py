"""Integration tests against real fixture images using PaddleOCR.

Requires PaddleOCR to be installed and fixture images to be present.
Run with: pytest tests/test_integration.py -m integration
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "golden_set" / "cases.jsonl"

pytestmark = pytest.mark.integration


def load_case(case_id: str) -> dict:
    with CASES_PATH.open() as f:
        for line in f:
            case = json.loads(line)
            if case["inputs"]["case_id"] == case_id:
                return case
    raise KeyError(f"Case {case_id} not found")


def resolve_image_path(rel_path: str) -> str:
    candidate = Path(rel_path)
    if candidate.is_absolute():
        return str(candidate)
    return str((ROOT / rel_path).resolve())


def run_case(case_id: str) -> tuple[dict, dict]:
    """Returns (actual, expected)."""
    from alc_label_verifier.service import verify_label

    case = load_case(case_id)
    inputs = case["inputs"]
    expected = case["outputs"]

    image_path = resolve_image_path(inputs["label_image_path"])
    actual = verify_label(image_path, inputs["application"])
    return actual, expected


class TestFocusedIntegrationSubset:
    """The six priority cases from the M1 test plan."""

    def test_gs_001_clean_match(self):
        actual, expected = run_case("gs_001")
        assert actual["overall_verdict"] == expected["overall_verdict"], (
            f"Verdict: got {actual['overall_verdict']}, expected {expected['overall_verdict']}"
        )
        assert actual["recommended_action"] == expected["recommended_action"]
        assert actual["field_results"]["country_of_origin"]["status"] == "not_applicable"

    def test_gs_007_brand_normalization(self):
        actual, expected = run_case("gs_007")
        assert actual["overall_verdict"] == expected["overall_verdict"]
        br = actual["field_results"]["brand_name"]
        assert br["status"] == "match"
        assert br["reason_code"] == "normalized_match"

    def test_gs_010_alcohol_normalization(self):
        actual, expected = run_case("gs_010")
        assert actual["overall_verdict"] == expected["overall_verdict"]
        alc = actual["field_results"]["alcohol_content"]
        assert alc["status"] == "match"
        assert alc["reason_code"] == "normalized_match"

    def test_gs_018_warning_prefix_error(self):
        actual, expected = run_case("gs_018")
        assert actual["overall_verdict"] == "mismatch"
        gw = actual["field_results"]["government_warning"]
        assert gw["status"] == "mismatch"
        assert gw["reason_code"] == "warning_prefix_error"

    def test_gs_020_warning_partial_occlusion(self):
        actual, expected = run_case("gs_020")
        assert actual["overall_verdict"] == "needs_review"
        gw = actual["field_results"]["government_warning"]
        assert gw["status"] == "needs_review"
        assert gw["reason_code"] == "unreadable"

    def test_gs_026_missing_required_country(self):
        actual, expected = run_case("gs_026")
        assert actual["overall_verdict"] == "mismatch"
        co = actual["field_results"]["country_of_origin"]
        assert co["status"] == "mismatch"
        assert co["reason_code"] == "missing_required"
