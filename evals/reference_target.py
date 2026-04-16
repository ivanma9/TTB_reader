"""Reference target for smoke-testing the golden-set harness.

This is intentionally not a real verifier. It mirrors the expected outputs in
the golden set so the runner and evaluators can be validated independently from
the application agent.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any, Dict

from evals.golden_set.evaluators import load_cases
from evals.golden_set.schema import DEFAULT_CASES_PATH


@lru_cache(maxsize=1)
def _expected_outputs_by_case() -> Dict[str, Dict[str, Any]]:
    cases = load_cases(DEFAULT_CASES_PATH)
    return {
        case["inputs"]["case_id"]: deepcopy(case["outputs"])
        for case in cases
    }


def target(inputs: Dict[str, Any]) -> Dict[str, Any]:
    case_id = inputs.get("case_id")
    if not case_id:
        raise ValueError("Reference target requires `case_id` in inputs.")

    try:
        output = deepcopy(_expected_outputs_by_case()[case_id])
    except KeyError as exc:
        raise KeyError(f"Unknown golden-set case_id: {case_id}") from exc

    output["_target"] = "reference_target"
    return output

