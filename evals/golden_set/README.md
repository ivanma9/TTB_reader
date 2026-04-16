# Golden Set Evals

This directory contains the v1 distilled-spirits golden set for the alcohol
label verifier.

## Files
- `cases.jsonl`: local source of truth for the 28 authored evaluation cases
- `fixtures/`: synthetic label PNGs for each case
- `build_golden_set.py`: deterministic builder for the dataset and image fixtures
- `evaluators.py`: local and LangSmith-compatible evaluators
- `../run_golden_set.py`: local runner plus optional LangSmith experiment runner

## Rebuild The Dataset
```bash
python3 -m evals.golden_set.build_golden_set
```

## Run Locally
This defaults to the reference target, which mirrors expected outputs and is
useful for smoke-testing the harness.

```bash
python3 evals/run_golden_set.py
```

To point the runner at a real verifier:

```bash
ALC_EVAL_TARGET=your_module:target python3 evals/run_golden_set.py
```

## Run In LangSmith
Install the SDK, set `LANGSMITH_API_KEY`, and optionally `LANGSMITH_WORKSPACE_ID`.

```bash
python3 -m pip install langsmith
python3 evals/run_golden_set.py --mode langsmith --upsert-dataset
```

## Output Contract
The evals assume the verifier returns:
- `overall_verdict`
- `recommended_action`
- `field_results` for all seven tracked fields

Free-form explanations can be returned by the agent, but they are not scored.
