# PRD 03: Batch Review Beta

## Objective
- Expand the single-label MVP into a lightweight batch workflow that lets reviewers process multiple labels in one session without sacrificing the clarity or reliability of the core verification experience.

## Preconditions
- Assumes PRD 01 and PRD 02 are complete and stable. M3 extends orchestration and navigation around the existing verifier and single-label result model; it does not reopen engine scope, beverage scope, or result semantics.

## Target Users
- Primary user persona: compliance agents or importer-side operators handling multiple labels in a sitting.
- Secondary persona: reviewers assessing whether the prototype has a credible path beyond a one-off happy-path demo.

## Scope
### In Scope (MVP)
- Upload and process up to 10 label images in one session.
- A sequential, session-scoped queue built on the same single-label verifier contract and the same distilled-spirits-only field set from M1 and M2.
- Per-label expected-data entry or editing within the session.
- Batch summary view showing counts for:
  - Match
  - Mismatch
  - Needs review
- Visual highlighting for rows whose recommended action is `manual review` or `request better image`.
- Per-label drill-down into the same field-by-field result detail used in the single-label MVP.
- Graceful partial-failure handling so one bad label does not block the rest of the batch.

### Out of Scope (Non-goals)
- Expanding beverage coverage, tracked fields, or core result semantics beyond the M1/M2 contract.
- Background jobs spanning multiple sessions.
- True enterprise-scale throughput tuning.
- Direct import from COLA or other source systems.
- Multi-user collaboration, assignment, or audit workflows.
- Automatic export integrations.

## Functional Requirements
| ID | Requirement | Priority (Must/Should/Could) | Acceptance Criteria |
|---|---|---|---|
| FR-1 | User can add multiple label images in one session | Must | The app accepts at least 10 images and creates a distinct review row for each label |
| FR-2 | Each label can be verified independently using the existing engine | Must | Every row uses the existing verifier contract and reaches a terminal state even if other rows fail or require review |
| FR-3 | Batch status is visible at a glance | Must | The summary view shows counts by verdict (`match`, `mismatch`, `needs_review`) and highlights rows whose recommended action is `manual review` or `request better image` |
| FR-4 | Reviewer can drill into any label for detailed reasoning | Must | Selecting a label opens the same field-by-field detail model and next-action guidance used in the single-label workflow |
| FR-5 | Batch processing does not regress the single-label path | Must | The single-label experience remains available and retains its performance and clarity |
| FR-6 | Processing is sequential for demo stability | Should | The app processes one label at a time from a visible queue; no parallel workers are required in beta |
| FR-7 | Reviewers can capture or export a simple session summary | Could | The app can provide a CSV or copyable summary table for follow-up review |

## Success Metrics
| Metric | Baseline | MVP Target |
|---|---|---|
| Labels supported per batch | 1 | 10 |
| Batch completion time for 10 routine labels | No batch mode | <= 60 seconds typical |
| Labels reaching a terminal state in batch | No batch mode | 100% |
| Time to identify items needing review | No batch mode | <= 1 click from summary |
| Single-label latency regression after adding batch | 0% baseline | <= 10% regression |

## Measurement Plan
- `Labels supported per batch`: verified by creating a 10-image session and confirming all rows can be queued and reviewed without falling back to the single-label screen.
- `Batch completion time for 10 routine labels`: measured from pressing the batch run action on a prepared 10-label session, with expected data already entered, until the last row reaches a terminal state.
- `Labels reaching a terminal state in batch`: verified with at least one 10-label run that includes match, mismatch, unreadable, and low-confidence/manual-review cases; no row may remain stuck because another row failed.
- `Time to identify items needing review`: measured from the batch summary to the first row whose recommended action is `manual review` or `request better image`; target remains no more than one click.
- `Single-label latency regression after adding batch`: measured by rerunning the PRD 02 single-label timing check after batch lands and comparing typical latency to the pre-batch baseline.

## Release Plan
- Internal alpha: batch session model exists with simple queueing and shared verifier logic.
- Beta: batch summary and drill-down are demoable and stable on representative data.
- MVP launch: included only if the single-label path is already stable and submission packaging is complete.

## Risks and Tradeoffs
| Risk/Tradeoff | Decision | Rationale |
|---|---|---|
| Batch can easily consume the time budget | Treat batch as a conditional milestone after MVP stability | The presearch explicitly favors a polished core over breadth |
| Multi-label expected-data entry can become cumbersome | Keep the first version simple and session-scoped instead of designing a full import pipeline | This preserves usefulness without dragging the project into data-integration work |
| Parallel processing could destabilize the demo | Prefer a visible sequential queue in beta; revisit bounded concurrency later | Predictability matters more than maximum throughput in a take-home setting |
| Summary UX can hide important errors | Make manual-review and better-image counts visually prominent | The point of batch mode is triage, not only throughput |

## Default Beta Decisions
- Scope inheritance: batch reuses the distilled-spirits-only, seven-field verifier contract and the same verdict and recommended-action model from M1 and M2. Do not expand beverage scope or redefine results in beta.
- Data entry: use inline per-row expected-data editing in the beta. Do not build CSV import in the first pass.
- Summary model: group batch counts by verdict (`match`, `mismatch`, `needs_review`) and separately highlight rows whose recommended action is `manual review` or `request better image`.
- Processing model: use a sequential queue for Day 5 implementation. Revisit concurrency only if batch becomes a post-take-home extension.
- Export surface: do not build export in the beta unless Day 5 ends early with the core batch flow already stable.
