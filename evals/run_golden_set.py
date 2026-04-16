"""Run the distilled-spirits golden-set eval locally or in LangSmith."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.adapter import resolve_target
from evals.golden_set.evaluators import (
    all_case_evaluators,
    gate_results,
    load_cases,
    resolve_fixture_path,
    score_prediction,
    summarize_case_results,
)
from evals.golden_set.schema import (
    DEFAULT_CASES_PATH,
    DEFAULT_DATASET_NAME,
    DEFAULT_EXPERIMENT_PREFIX,
    DEFAULT_LANGSMITH_PROJECT,
    ROOT_DIR,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "langsmith"), default="local")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--target-spec", default=None, help="Override target as module:function")
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--experiment-prefix", default=DEFAULT_EXPERIMENT_PREFIX)
    parser.add_argument("--langsmith-project", default=DEFAULT_LANGSMITH_PROJECT)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--upsert-dataset", action="store_true")
    return parser.parse_args()


def _set_target_override(target_spec: str | None) -> None:
    if target_spec:
        os.environ["ALC_EVAL_TARGET"] = target_spec
        resolve_target.cache_clear()


def _prepare_inputs(case_inputs: Mapping[str, Any]) -> Dict[str, Any]:
    prepared = copy.deepcopy(dict(case_inputs))
    prepared["label_image_path"] = resolve_fixture_path(prepared["label_image_path"], ROOT_DIR)
    return prepared


def run_local(cases: List[Mapping[str, Any]]) -> int:
    target = resolve_target()
    case_results: List[Dict[str, Any]] = []

    for case in cases:
        prepared_inputs = _prepare_inputs(case["inputs"])
        actual = target(prepared_inputs)
        result = score_prediction(
            inputs=case["inputs"],
            actual=actual,
            expected=case["outputs"],
        )
        case_results.append(result)

    summary = summarize_case_results(case_results)
    gates = gate_results(summary)

    print(json.dumps({"summary": summary, "gates": gates}, indent=2))
    failing_contracts = [
        {
            "case_id": result["case_id"],
            "contract_errors": result["contract_errors"],
        }
        for result in case_results
        if result["contract_errors"]
    ]
    if failing_contracts:
        print(json.dumps({"contract_errors": failing_contracts}, indent=2))

    return 0 if all(gates.values()) and not failing_contracts else 1


def _import_langsmith():
    try:
        from langsmith import Client
    except ImportError as exc:
        raise RuntimeError(
            "LangSmith mode requires `langsmith` to be installed. "
            "Install it with `python3 -m pip install langsmith`."
        ) from exc
    return Client


def _ensure_dataset(client: Any, dataset_name: str, cases: List[Mapping[str, Any]]) -> None:
    datasets = list(client.list_datasets(dataset_name=dataset_name))
    dataset = datasets[0] if datasets else None

    if dataset is None:
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description="Golden-set distilled spirits MVP dataset for alcohol label verification.",
        )
        examples = [
            {
                "inputs": case["inputs"],
                "outputs": case["outputs"],
                "metadata": case.get("metadata", {}),
            }
            for case in cases
        ]
        client.create_examples(dataset_id=dataset.id, examples=examples)
        return

    existing_examples = list(client.list_examples(dataset_id=dataset.id))
    by_case_id = {
        (example.metadata or {}).get("case_id") or example.inputs.get("case_id"): example
        for example in existing_examples
    }
    pending_creates: List[Dict[str, Any]] = []
    for case in cases:
        case_id = case["inputs"]["case_id"]
        if case_id in by_case_id:
            client.update_example(
                example_id=by_case_id[case_id].id,
                inputs=case["inputs"],
                outputs=case["outputs"],
                metadata=case.get("metadata", {}),
            )
        else:
            pending_creates.append(
                {
                    "inputs": case["inputs"],
                    "outputs": case["outputs"],
                    "metadata": case.get("metadata", {}),
                }
            )
    if pending_creates:
        client.create_examples(dataset_id=dataset.id, examples=pending_creates)


def run_langsmith(cases: List[Mapping[str, Any]], args: argparse.Namespace) -> int:
    Client = _import_langsmith()
    os.environ.setdefault("LANGSMITH_PROJECT", args.langsmith_project)
    client = Client()

    if args.upsert_dataset:
        _ensure_dataset(client, args.dataset_name, cases)

    target = resolve_target()

    def traced_target(inputs: Dict[str, Any]) -> Dict[str, Any]:
        return target(_prepare_inputs(inputs))

    results = client.evaluate(
        traced_target,
        data=args.dataset_name,
        evaluators=all_case_evaluators(),
        experiment_prefix=args.experiment_prefix,
        max_concurrency=args.max_concurrency,
    )
    print(results)
    return 0


def main() -> int:
    args = parse_args()
    _set_target_override(args.target_spec)
    cases = load_cases(args.cases)

    if args.mode == "langsmith":
        return run_langsmith(cases, args)
    return run_local(cases)


if __name__ == "__main__":
    raise SystemExit(main())
