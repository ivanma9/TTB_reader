"""Contract tests: every verifier response must satisfy the eval harness schema."""

import pytest
from alc_label_verifier._constants import FIELD_NAMES
from evals.golden_set.evaluators import validate_prediction_contract


def _minimal_application(is_import: bool = False) -> dict:
    return {
        "beverage_type": "distilled_spirits",
        "brand_name": "TEST BRAND",
        "class_type": "Test Whiskey",
        "alcohol_content": "40% Alc./Vol. (80 Proof)",
        "net_contents": "750 mL",
        "producer_name_address": "Test Distillery, Springfield, USA",
        "is_import": is_import,
        "country_of_origin": None,
        "government_warning": (
            "GOVERNMENT WARNING: According to the Surgeon General, women should not "
            "drink alcoholic beverages during pregnancy because of the risk of birth "
            "defects. Consumption of alcoholic beverages impairs your ability to drive "
            "a car or operate machinery, and may cause health problems."
        ),
    }


def _mock_all_match_response() -> dict:
    """Build a synthetic response that should pass all contract checks."""
    field_results = {name: {"status": "match", "reason_code": "exact_match"} for name in FIELD_NAMES}
    field_results["country_of_origin"] = {"status": "not_applicable", "reason_code": "not_applicable"}
    return {
        "overall_verdict": "match",
        "recommended_action": "accept",
        "field_results": field_results,
    }


def _mock_all_unreadable_response() -> dict:
    field_results = {name: {"status": "needs_review", "reason_code": "unreadable"} for name in FIELD_NAMES}
    return {
        "overall_verdict": "needs_review",
        "recommended_action": "request_better_image",
        "field_results": field_results,
    }


class TestContractShape:
    def test_match_response_passes_contract(self):
        output = _mock_all_match_response()
        errors = validate_prediction_contract(output)
        assert errors == [], f"Contract errors: {errors}"

    def test_unreadable_response_passes_contract(self):
        output = _mock_all_unreadable_response()
        errors = validate_prediction_contract(output)
        assert errors == [], f"Contract errors: {errors}"

    def test_missing_overall_verdict_fails(self):
        output = _mock_all_match_response()
        del output["overall_verdict"]
        errors = validate_prediction_contract(output)
        assert any("overall_verdict" in e for e in errors)

    def test_missing_recommended_action_fails(self):
        output = _mock_all_match_response()
        del output["recommended_action"]
        errors = validate_prediction_contract(output)
        assert any("recommended_action" in e for e in errors)

    def test_missing_field_results_fails(self):
        output = _mock_all_match_response()
        del output["field_results"]
        errors = validate_prediction_contract(output)
        assert any("field_results" in e for e in errors)

    def test_missing_one_field_fails(self):
        output = _mock_all_match_response()
        del output["field_results"]["brand_name"]
        errors = validate_prediction_contract(output)
        assert any("brand_name" in e for e in errors)

    def test_missing_status_in_field_fails(self):
        output = _mock_all_match_response()
        del output["field_results"]["class_type"]["status"]
        errors = validate_prediction_contract(output)
        assert any("class_type" in e and "status" in e for e in errors)

    def test_all_seven_fields_required(self):
        output = _mock_all_match_response()
        assert set(FIELD_NAMES) == set(output["field_results"].keys())
