"""Per-field failure breakdown for the real-labels eval.

Runs the verifier against every case in evals/real_labels/cases.jsonl and
writes a CSV + per-field summary to help triage which matcher breaks most
often on real imagery.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping

from evals.golden_set.evaluators import resolve_fixture_path
from evals.golden_set.schema import FIELD_NAMES, ROOT_DIR
from alc_label_verifier.adapter import target as verify_target

CASES_PATH = ROOT_DIR / "evals" / "real_labels" / "cases.jsonl"
GAPS_DIR = ROOT_DIR / "docs"
GAPS_CSV = GAPS_DIR / "real-label-gaps.csv"
GAPS_MD = GAPS_DIR / "real-label-gaps.md"


def _load_cases() -> List[Dict[str, Any]]:
    with CASES_PATH.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _run_verifier(case: Mapping[str, Any]) -> Dict[str, Any]:
    inputs = dict(case["inputs"])
    inputs["label_image_path"] = resolve_fixture_path(
        inputs["label_image_path"], ROOT_DIR
    )
    return verify_target(inputs)


def main() -> int:
    cases = _load_cases()

    rows: List[Dict[str, Any]] = []
    field_status_counts: Dict[str, Counter] = defaultdict(Counter)
    field_reason_on_fail: Dict[str, Counter] = defaultdict(Counter)
    verdict_counter: Counter = Counter()
    action_counter: Counter = Counter()

    for case in cases:
        case_id = case["inputs"]["case_id"]
        expected = case["outputs"]
        actual = _run_verifier(case)

        verdict_counter[actual.get("overall_verdict")] += 1
        action_counter[actual.get("recommended_action")] += 1

        row: Dict[str, Any] = {
            "case_id": case_id,
            "ttb_id": case["metadata"].get("ttb_id"),
            "is_import": case["inputs"]["application"].get("is_import"),
            "expected_verdict": expected["overall_verdict"],
            "actual_verdict": actual.get("overall_verdict"),
            "expected_action": expected["recommended_action"],
            "actual_action": actual.get("recommended_action"),
        }

        for field in FIELD_NAMES:
            exp = expected["field_results"].get(field, {})
            act = actual.get("field_results", {}).get(field, {})
            exp_status = exp.get("status")
            act_status = act.get("status")
            act_reason = act.get("reason_code")
            observed = act.get("observed_value")

            row[f"{field}_expected"] = exp_status
            row[f"{field}_actual"] = act_status
            row[f"{field}_reason"] = act_reason
            row[f"{field}_observed"] = observed

            field_status_counts[field][act_status] += 1
            if act_status != exp_status:
                field_reason_on_fail[field][act_reason or "none"] += 1

        rows.append(row)

    GAPS_DIR.mkdir(parents=True, exist_ok=True)

    if rows:
        with GAPS_CSV.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    total = len(cases)
    lines: List[str] = []
    lines.append("# Real-label eval gaps\n")
    lines.append(f"Cases: **{total}** (source: TTB COLA 2017 demo via Kaggle)\n")
    lines.append("\n## Overall verdict distribution\n")
    for verdict, n in verdict_counter.most_common():
        lines.append(f"- `{verdict}`: {n}")
    lines.append("\n## Recommended-action distribution\n")
    for action, n in action_counter.most_common():
        lines.append(f"- `{action}`: {n}")

    lines.append("\n## Per-field actual-status distribution\n")
    lines.append("| Field | match | mismatch | needs_review | not_applicable |")
    lines.append("|-------|-------|----------|--------------|----------------|")
    for field in FIELD_NAMES:
        c = field_status_counts[field]
        lines.append(
            f"| {field} | {c.get('match',0)} | {c.get('mismatch',0)} | "
            f"{c.get('needs_review',0)} | {c.get('not_applicable',0)} |"
        )

    lines.append("\n## Top failure reasons per field\n")
    for field in FIELD_NAMES:
        reasons = field_reason_on_fail.get(field)
        if not reasons:
            continue
        lines.append(f"\n### {field}")
        for reason, n in reasons.most_common(5):
            lines.append(f"- `{reason}`: {n}")

    lines.append(
        f"\n---\n\nPer-case details: `{GAPS_CSV.relative_to(ROOT_DIR)}`\n"
    )

    with GAPS_MD.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Wrote {GAPS_CSV}")
    print(f"Wrote {GAPS_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
