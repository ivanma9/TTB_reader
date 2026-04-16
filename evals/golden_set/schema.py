"""Shared schema constants for the distilled-spirits golden set."""

from __future__ import annotations

from pathlib import Path

FIELD_NAMES = (
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name_address",
    "country_of_origin",
    "government_warning",
)

STATUS_VALUES = ("match", "mismatch", "needs_review", "not_applicable")
RECOMMENDED_ACTION_VALUES = ("accept", "manual_review", "request_better_image")
REASON_CODE_VALUES = (
    "exact_match",
    "normalized_match",
    "wrong_value",
    "missing_required",
    "not_applicable",
    "unreadable",
    "warning_prefix_error",
    "warning_text_mismatch",
)

DEFAULT_LANGSMITH_PROJECT = "alc-label-verifier"
DEFAULT_DATASET_NAME = "golden-mvp-distilled-spirits-v1"
DEFAULT_EXPERIMENT_PREFIX = "golden-mvp-v1"

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = ROOT_DIR / "evals" / "golden_set" / "cases.jsonl"
DEFAULT_FIXTURES_DIR = ROOT_DIR / "evals" / "golden_set" / "fixtures"

METRIC_GATES = {
    "overall_verdict_accuracy": 0.93,
    "field_status_accuracy": 0.90,
    "warning_strictness_accuracy": 1.0,
    "conditional_rule_accuracy": 1.0,
    "unreadable_fallback_accuracy": 1.0,
    "false_hard_fail_on_unreadable": 0,
}

