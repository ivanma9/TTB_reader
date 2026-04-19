# PRD 02: Single-Label Reviewer Workbench

## Objective
- Deliver a polished single-label verification workflow that lets a compliance reviewer upload one alcohol label, enter expected distilled-spirits application data, and receive a clear pass, mismatch, or needs-review result within the flow of work.

## Target Users
- Primary user persona: TTB label compliance agent with mixed technical comfort and limited patience for complex tooling.
- Secondary persona: take-home reviewer evaluating whether the prototype solves a real workflow cleanly and credibly.

## Scope
### In Scope (MVP)
- Single-label upload for one front-facing label image.
- Manual entry or paste of expected application data for the distilled-spirits MVP fields.
- Beverage scope fixed to distilled spirits in v1 so the workflow is explicit and predictable.
- Reviewer-visible result states:
  - Match
  - Mismatch
  - Needs review
- Field-by-field reasoning that distinguishes normalization-based matches from strict mismatches.
- Clear fallback behavior for unreadable images, missing text, or uncertain extractions.
- Local-first verification path with no required COLA integration.
- Fast, low-navigation interface optimized for one task.

### Out of Scope (Non-goals)
- Beer and wine coverage.
- Multi-label batch intake.
- User accounts, permissions, or audit trails.
- Automatic application-data import from COLA or other systems.
- Production-grade federal deployment constraints such as FedRAMP controls.

## Functional Requirements
| ID | Requirement | Priority (Must/Should/Could) | Acceptance Criteria |
|---|---|---|---|
| FR-1 | Reviewer can upload one label image and enter the expected distilled-spirits fields | Must | The form captures all seven tracked fields and makes optional or conditional inputs obvious |
| FR-2 | Reviewer can run verification with a single primary action | Must | The app exposes one obvious run action and shows progress until a result is returned |
| FR-3 | The result view shows overall verdict plus field-by-field statuses | Must | Each field is labeled as `match`, `mismatch`, `needs_review`, or `not_applicable` with a short explanation |
| FR-4 | The UI surfaces recommended next action, not only a binary answer | Must | The app shows whether the reviewer should accept, manually review, or request a better image |
| FR-5 | Government warning validation is treated strictly and clearly | Must | Warning-prefix errors and warning-text deviations are surfaced distinctly from generic mismatches |
| FR-6 | Unreadable-image handling is explicit | Must | Low-confidence cases return a visible `needs_review` or `request better image` outcome instead of failing silently |
| FR-7 | The app is fast enough for routine use | Must | Typical end-to-end single-label checks complete in about 5 seconds or less |
| FR-8 | The app does not require external network calls for core verification | Should | The core demo path works in a standalone environment using local processing only |
| FR-9 | The app minimizes retained data | Should | Uploaded images remain session-scoped by default and are not kept longer than necessary for the prototype flow |

## Success Metrics
| Metric | Baseline | MVP Target |
|---|---|---|
| End-to-end single-label latency | No app yet | <= 5 seconds typical |
| Golden-set verifier gate pass rate | 0.00 | Meets all existing MVP gates before UI signoff |
| Result rows with clear explanation | No app yet | 100% |
| Silent failure rate on unreadable inputs | Unknown | 0 |
| Fresh-session walkthrough time (self-run dry run) | Unknown | <= 2 minutes |

## Measurement Plan
- `End-to-end single-label latency`: measured with 10 timed local runs across 5 representative readable fixtures after the Day 4 UI freeze.
- `Golden-set verifier gate pass rate`: measured by running `python3 evals/run_golden_set.py` against the production verifier before UI signoff.
- `Result rows with clear explanation`: verified with a 5-case manual checklist covering match, mismatch, import, warning, and unreadable scenarios.
- `Silent failure rate on unreadable inputs`: verified using unreadable golden-set cases and one manual UI run where the image is intentionally degraded.
- `Fresh-session walkthrough time`: measured by following the quick-start path once in a clean browser session on Day 4.

## Release Plan
- Internal alpha: UI shell connected to a working verifier with dummy or early real data.
- Beta: full happy path working for distilled spirits with readable error and fallback states.
- MVP launch: deployed single-label workflow with final docs and demo-ready sample inputs.

## Risks and Tradeoffs
| Risk/Tradeoff | Decision | Rationale |
|---|---|---|
| More fields can make the form feel heavy | Keep the workflow single-purpose and visually guided | Reviewers tolerate forms better when the page is focused and explanations are obvious |
| Showing too much OCR detail could confuse the reviewer | Surface field-level reasoning, not OCR internals by default | The reviewer needs confidence and clarity, not pipeline mechanics |
| Automatic beverage inference could be error-prone | Make distilled-spirits scope explicit in MVP | Clear scope is safer than a clever but fragile inference layer |
| Persistent storage could create avoidable privacy concerns | Favor session-scoped processing for the prototype | This matches the standalone, low-retention posture described in presearch |

## Default UX Decisions
- Beverage type: fixed to distilled spirits in v1. Do not expose a broader beverage selector until the rules engine actually supports it.
- Evidence display: show field status, short reason, and extracted snippet only for mismatches or `needs_review` cases.
- Raw OCR visibility: do not build a side-by-side OCR text panel in v1; at most, expose raw OCR text behind a collapsed debug section.
