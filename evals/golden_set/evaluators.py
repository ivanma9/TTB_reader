"""Golden-set evaluators for the alcohol label verifier."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

from evals.golden_set.schema import DEFAULT_CASES_PATH, FIELD_NAMES, METRIC_GATES


def load_cases(path: Path | str = DEFAULT_CASES_PATH) -> List[Dict[str, Any]]:
    cases_path = Path(path)
    with cases_path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def resolve_fixture_path(label_image_path: str, root_dir: Path) -> str:
    candidate = Path(label_image_path)
    if candidate.is_absolute():
        return str(candidate)
    return str((root_dir / candidate).resolve())


def _deepcopy_mapping(value: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return deepcopy(dict(value or {}))


def _extract_payload(
    *args: Any,
    **kwargs: Any,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    if len(args) == 2 and hasattr(args[0], "outputs") and hasattr(args[1], "outputs"):
        run, example = args
        return (
            _deepcopy_mapping(getattr(example, "inputs", {})),
            _deepcopy_mapping(getattr(run, "outputs", {})),
            _deepcopy_mapping(getattr(example, "outputs", {})),
        )

    if len(args) >= 3:
        return (
            _deepcopy_mapping(args[0]),
            _deepcopy_mapping(args[1]),
            _deepcopy_mapping(args[2]),
        )

    return (
        _deepcopy_mapping(kwargs.get("inputs")),
        _deepcopy_mapping(kwargs.get("outputs")),
        _deepcopy_mapping(kwargs.get("reference_outputs")),
    )


def _metric(key: str, score: float | int | bool | None, comment: str = "") -> Dict[str, Any]:
    metric = {"key": key, "score": score}
    if comment:
        metric["comment"] = comment
    return metric


def _field_results(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return payload.get("field_results", {}) or {}


def _field_status(field_payload: Mapping[str, Any]) -> Optional[str]:
    return field_payload.get("status")


def _field_reason(field_payload: Mapping[str, Any]) -> Optional[str]:
    return field_payload.get("reason_code")


def _case_tags(expected: Mapping[str, Any]) -> set[str]:
    return set(expected.get("expected_tags", []) or [])


def overall_verdict_accuracy(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    _, actual, expected = _extract_payload(*args, **kwargs)
    score = int(actual.get("overall_verdict") == expected.get("overall_verdict"))
    comment = f"expected={expected.get('overall_verdict')} actual={actual.get('overall_verdict')}"
    return _metric("overall_verdict_accuracy", score, comment)


def field_status_accuracy(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    _, actual, expected = _extract_payload(*args, **kwargs)
    actual_fields = _field_results(actual)
    expected_fields = _field_results(expected)

    matches = 0
    mismatched_fields: List[str] = []
    for field_name in FIELD_NAMES:
        if _field_status(actual_fields.get(field_name, {})) == _field_status(expected_fields.get(field_name, {})):
            matches += 1
        else:
            mismatched_fields.append(field_name)

    score = matches / len(FIELD_NAMES)
    comment = "all field statuses match" if not mismatched_fields else f"mismatched={','.join(mismatched_fields)}"
    return _metric("field_status_accuracy", score, comment)


def recommended_action_accuracy(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    _, actual, expected = _extract_payload(*args, **kwargs)
    score = int(actual.get("recommended_action") == expected.get("recommended_action"))
    comment = f"expected={expected.get('recommended_action')} actual={actual.get('recommended_action')}"
    return _metric("recommended_action_accuracy", score, comment)


def warning_strictness_accuracy(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    _, actual, expected = _extract_payload(*args, **kwargs)
    tags = _case_tags(expected)
    if not {
        "warning_exact",
        "warning_prefix_error",
        "warning_text_deviation",
        "warning_partial_occlusion",
    } & tags:
        return _metric("warning_strictness_accuracy", None, "N/A - non-warning case")

    actual_warning = _field_results(actual).get("government_warning", {})
    expected_warning = _field_results(expected).get("government_warning", {})
    score = int(
        _field_status(actual_warning) == _field_status(expected_warning)
        and _field_reason(actual_warning) == _field_reason(expected_warning)
    )
    comment = (
        f"expected=({_field_status(expected_warning)},{_field_reason(expected_warning)}) "
        f"actual=({_field_status(actual_warning)},{_field_reason(actual_warning)})"
    )
    return _metric("warning_strictness_accuracy", score, comment)


def conditional_rule_accuracy(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    _, actual, expected = _extract_payload(*args, **kwargs)
    tags = _case_tags(expected)
    if not {"import_required", "domestic_not_applicable"} & tags:
        return _metric("conditional_rule_accuracy", None, "N/A - non-conditional case")

    actual_country = _field_results(actual).get("country_of_origin", {})
    expected_country = _field_results(expected).get("country_of_origin", {})
    score = int(
        _field_status(actual_country) == _field_status(expected_country)
        and _field_reason(actual_country) == _field_reason(expected_country)
    )
    comment = (
        f"expected=({_field_status(expected_country)},{_field_reason(expected_country)}) "
        f"actual=({_field_status(actual_country)},{_field_reason(actual_country)})"
    )
    return _metric("conditional_rule_accuracy", score, comment)


def unreadable_fallback_accuracy(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    _, actual, expected = _extract_payload(*args, **kwargs)
    tags = _case_tags(expected)
    if "unreadable_image" not in tags:
        return _metric("unreadable_fallback_accuracy", None, "N/A - readable case")

    predicted_verdict = actual.get("overall_verdict")
    predicted_action = actual.get("recommended_action")
    expected_verdict = expected.get("overall_verdict")
    expected_action = expected.get("recommended_action")

    hard_fail = predicted_verdict == "mismatch" or predicted_action == "accept"
    score = int(
        not hard_fail
        and predicted_verdict == expected_verdict
        and predicted_action == expected_action
    )
    comment = (
        f"expected=({expected_verdict},{expected_action}) "
        f"actual=({predicted_verdict},{predicted_action})"
    )
    return _metric("unreadable_fallback_accuracy", score, comment)


def all_case_evaluators() -> List[Any]:
    return [
        overall_verdict_accuracy,
        field_status_accuracy,
        recommended_action_accuracy,
        warning_strictness_accuracy,
        conditional_rule_accuracy,
        unreadable_fallback_accuracy,
    ]


def validate_prediction_contract(output: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []

    if "overall_verdict" not in output:
        errors.append("Missing `overall_verdict`.")
    if "recommended_action" not in output:
        errors.append("Missing `recommended_action`.")
    if "field_results" not in output:
        errors.append("Missing `field_results`.")
        return errors

    field_results = _field_results(output)
    for field_name in FIELD_NAMES:
        if field_name not in field_results:
            errors.append(f"Missing field_results entry for `{field_name}`.")
            continue
        field_payload = field_results[field_name] or {}
        if "status" not in field_payload:
            errors.append(f"Missing status for `{field_name}`.")
        if "reason_code" not in field_payload:
            errors.append(f"Missing reason_code for `{field_name}`.")

    return errors


def score_prediction(
    *,
    inputs: Mapping[str, Any],
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> Dict[str, Any]:
    metrics = [
        evaluator(inputs, actual, expected)
        for evaluator in all_case_evaluators()
    ]
    return {
        "case_id": inputs.get("case_id"),
        "metrics": metrics,
        "contract_errors": validate_prediction_contract(actual),
    }


def summarize_case_results(case_results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    metric_values: MutableMapping[str, List[float]] = {}
    unreadable_hard_fail_count = 0
    failing_cases: List[str] = []

    for result in case_results:
        case_id = str(result.get("case_id"))
        metrics = result.get("metrics", [])
        contract_errors = result.get("contract_errors", [])
        if contract_errors:
            failing_cases.append(case_id)

        for metric in metrics:
            score = metric.get("score")
            if score is None:
                continue
            metric_values.setdefault(metric["key"], []).append(float(score))

        unreadable_metric = next(
            (metric for metric in metrics if metric.get("key") == "unreadable_fallback_accuracy"),
            None,
        )
        if unreadable_metric and unreadable_metric.get("score") == 0:
            unreadable_hard_fail_count += 1
            failing_cases.append(case_id)

    summary = {
        metric_name: (mean(scores) if scores else None)
        for metric_name, scores in metric_values.items()
    }
    summary["false_hard_fail_on_unreadable"] = unreadable_hard_fail_count
    summary["failing_cases"] = sorted(set(failing_cases))
    return summary


def gate_results(summary: Mapping[str, Any]) -> Dict[str, bool]:
    gate_status: Dict[str, bool] = {}
    for metric_name, threshold in METRIC_GATES.items():
        value = summary.get(metric_name)
        if value is None:
            gate_status[metric_name] = False
        elif metric_name == "false_hard_fail_on_unreadable":
            gate_status[metric_name] = value <= threshold
        else:
            gate_status[metric_name] = value >= threshold
    return gate_status
