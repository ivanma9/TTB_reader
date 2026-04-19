# PRD 01: Verification Engine Foundation

## Objective
- Prove that a standalone, local-first verifier can extract and validate distilled-spirits label fields accurately enough to support the reviewer-facing product.

## Target Users
- Primary user persona: internal builder validating technical feasibility before UI work.
- Secondary persona: prototype reviewer looking for evidence that the core engine is grounded in measurable quality, not only demo polish.

## Scope
### In Scope (MVP)
- Local OCR using PaddleOCR PP-OCRv5 mobile models with cached local weights, plus lightweight image preprocessing for single-label distilled-spirits fixtures.
- Deterministic validation rules for the seven tracked fields in the existing golden set:
  - `brand_name`
  - `class_type`
  - `alcohol_content`
  - `net_contents`
  - `producer_name_address`
  - `country_of_origin`
  - `government_warning`
- Separation between tolerant normalized matching and strict exact-text validation.
- Conditional rules for fields such as country of origin and government warning edge cases.
- A stable verifier output contract that works with `evals/run_golden_set.py`.
- Safe fallback behavior for unreadable or low-confidence images.

### Out of Scope (Non-goals)
- Reviewer UI or upload workflow.
- Beer and wine rule support.
- Direct COLA integration.
- Cloud-required OCR or hosted multimodal inference in the main path.
- Typography-level certainty, such as bold-style verification, when the chosen OCR stack cannot support it reliably.

## Functional Requirements
| ID | Requirement | Priority (Must/Should/Could) | Acceptance Criteria |
|---|---|---|---|
| FR-1 | The verifier accepts the label image plus expected application data and returns the full eval output contract | Must | Output contains `overall_verdict`, `recommended_action`, and `field_results` entries for all seven tracked fields |
| FR-2 | The verifier supports field-specific comparison strategies | Must | Tolerant normalization is applied only to approved fields, while strict validation remains in place for the government warning |
| FR-3 | The verifier supports conditional applicability rules | Must | `country_of_origin` returns `not_applicable` for domestic cases and is enforced for import-tagged cases |
| FR-4 | The verifier avoids hard mismatches on unreadable or low-confidence inputs | Must | Required fields below the confidence threshold return `needs_review`-style outcomes; unreadable-image eval cases never produce a false accept or hard mismatch |
| FR-5 | The verifier meets the existing distilled-spirits eval gates | Must | `evals/run_golden_set.py` passes the defined gate thresholds or produces a short documented gap list before UI work begins |
| FR-6 | The verifier runs fast enough to leave UI headroom | Should | Typical single-label verification completes in about 3 seconds or less on developer hardware |
| FR-7 | The verifier emits terse machine-readable reasons for each field status | Should | Each field result includes a `reason_code` that matches the repo contract and can be surfaced later in the UI |

## Success Metrics
| Metric | Baseline | MVP Target |
|---|---|---|
| `overall_verdict_accuracy` | 0.00 | >= 0.93 |
| `field_status_accuracy` | 0.00 | >= 0.90 |
| `warning_strictness_accuracy` | 0.00 | 1.00 |
| `conditional_rule_accuracy` | 0.00 | 1.00 |
| `unreadable_fallback_accuracy` | 0.00 | 1.00 |
| `false_hard_fail_on_unreadable` | Unknown | 0 |
| Typical local verification runtime | Unknown | <= 3 seconds |

## Release Plan
- Internal alpha: real verifier wired into the golden-set harness and producing valid contract output.
- Beta: verifier quality stabilized enough to freeze the engine interface for the reviewer UI.
- MVP launch: engine is treated as the authoritative backend for the single-label app.

## Measurement Plan
- End of Day 1: run a 10-case subset covering match, mismatch, warning, import, and unreadable cases to confirm the OCR stack choice and confidence policy.
- End of Day 2: run `python3 evals/run_golden_set.py` against the real verifier and record gate status plus failing cases.
- Runtime baseline: record median and p95 local verification time across 10 routine cases after the verifier contract stabilizes.

## Risks and Tradeoffs
| Risk/Tradeoff | Decision | Rationale |
|---|---|---|
| OCR may miss stylized or noisy text | Prefer conservative fallback over aggressive guessing | False confidence is more damaging than a `needs_review` result in a compliance workflow |
| Government warning formatting may exceed OCR certainty | Validate wording strictly, but mark formatting-only uncertainty for manual review | This preserves trust without pretending the prototype can see more than it can |
| A flexible universal rules engine would take too long | Build a distilled-spirits-first rule profile with extension points | It aligns to the take-home sample and keeps the engine shippable |
| Hosted AI could improve difficult cases | Keep the main path local-first and standalone | Network restrictions and explainability matter more than squeezing maximum extraction quality in v1 |

## Locked Execution Decisions
- OCR stack: use PaddleOCR PP-OCRv5 mobile detection and recognition locally with orientation classification enabled. Do not use a cloud OCR dependency in the main path.
- Confidence policy: for standard required fields, any best candidate below `0.80` confidence returns `needs_review`; for `government_warning`, require `0.90` confidence before issuing a hard mismatch because strictness matters more than recall.
- Preprocessing policy: start with grayscale conversion, contrast normalization, resize, and deskew or rotate; leave document unwarping off unless Day 1 eval failures show geometry is the dominant error source.
