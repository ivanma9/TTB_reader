# PRD 04: Submission and Reviewer Readiness

## Objective
- Package the prototype into a final product experience that reviewers can run, understand, and trust without hand-holding, while keeping the scope honest about what is and is not production-ready.

## Preconditions
- Assumes PRD 01 is complete and the verifier contract is stable enough to run the golden-set harness without reopening core field semantics.
- Assumes PRD 02 is complete or within one short finishing pass of complete. If the single-label reviewer flow is still missing a deployable surface, M4 may include only the minimum work required to make that flow runnable and reviewable.
- PRD 03 remains optional. Batch review may be shown only if it is already stable; M4 must not depend on batch shipping.

## Target Users
- Primary user persona: take-home reviewer assessing engineering quality, scope discipline, and product judgment.
- Secondary persona: future internal stakeholder who needs to understand the approach, tradeoffs, and path to expansion.

## Scope
### In Scope (MVP)
- Publicly accessible deployed application URL on a container-friendly host that supports local OCR runtime dependencies.
- README with setup, local run, eval instructions, and deployed-demo guidance.
- Short approach document covering architecture decisions, tools used, assumptions, and known tradeoffs.
- Seeded sample labels or demo fixtures, plus the matching expected application values or an equivalent guided demo path, so reviewers can reach the happy path quickly.
- Final smoke test across:
  - local app health and sample submission path
  - deployed UI
  - eval harness
- Explicit notes about retained limitations, especially beverage coverage, typography certainty, and privacy posture.

### Out of Scope (Non-goals)
- Production authentication and role-based access control.
- Government-grade retention, auditing, or FedRAMP controls.
- Legacy system integration.
- Ongoing analytics, monitoring, or incident tooling beyond lightweight demo checks.

## Functional Requirements
| ID | Requirement | Priority (Must/Should/Could) | Acceptance Criteria |
|---|---|---|---|
| FR-1 | Reviewers can access a live deployed demo | Must | A working URL is available and supports the single-label MVP flow without special credentials |
| FR-2 | The repository is runnable from the README | Must | A reviewer can create the documented environment, install dependencies, and start the app locally without undocumented steps |
| FR-3 | The project documents its decisions and tradeoffs clearly | Must | The repo contains concise notes on scope, chosen approach, assumptions, and non-goals |
| FR-4 | The demo path is easy to discover | Must | The repo or landing flow provides sample fixtures and matching expected values, or an equally obvious guided sample path, so reviewers can exercise the flow quickly |
| FR-5 | Final smoke checks cover both product and evaluation surfaces | Must | The team can run an automated smoke test for local health, seeded sample submission, golden-set execution, and deployed availability before submission |
| FR-6 | Privacy posture is explicit | Should | The docs state that images are processed with minimal retention and call out future hardening needs |
| FR-7 | The submission is resilient to light reviewer confusion | Should | The landing flow, README quick start, and approach note answer the most likely reviewer questions without requiring direct support |

## Success Metrics
| Metric | Baseline | MVP Target |
|---|---|---|
| Required submission artifacts complete | Partial | 100% |
| Time for reviewer to reach a working demo path | Unknown | <= 10 minutes |
| Time for clean-machine local setup | Unknown | <= 15 minutes |
| Broken-link or missing-step count in docs | Unknown | 0 |
| Consecutive smoke-test passes before handoff | 0 | 3 |

## Measurement Plan
- `Time for reviewer to reach a working demo path`: measured with a self-run dry run from the README quick start and a fresh browser session on Day 6.
- `Time for clean-machine local setup`: measured on a fresh virtual environment or container build using only the documented steps.
- `Broken-link or missing-step count`: verified by clicking every repo-local doc link and following every setup command once before handoff.
- `Consecutive smoke-test passes before handoff`: measured as three back-to-back successful runs of `scripts/smoke_test.sh` after the final candidate is deployed.

## Smoke Test Definition
- `scripts/smoke_test.sh` is created in M4 and must verify:
  - the app boots locally and exposes a health endpoint or equivalent readiness check
  - `python3 evals/run_golden_set.py` passes against the real verifier
  - one seeded sample label can be submitted locally and returns a terminal result
  - the deployed URL responds and the same seeded sample path is available there, or the deployed app exposes an equivalent publicly accessible demo route

## Release Gates
- README dry run: follow the quick-start instructions from a clean shell or container context and confirm they are complete without relying on unstated local setup.
- Demo dry run: open the deployed app in a fresh browser session and complete one seeded sample review using only the repo docs and on-screen guidance.
- Smoke stability: `scripts/smoke_test.sh` passes three times consecutively on the final candidate.

## Release Plan
- Internal dry run: another person or future-you follows the README from scratch and runs the seeded sample flow on the deployed demo.
- Reviewer-ready candidate: docs, deployment, and sample data are frozen except for bug fixes.
- Final submission: repo link, deployed URL, and supporting notes are all validated and handed off together.

## Risks and Tradeoffs
| Risk/Tradeoff | Decision | Rationale |
|---|---|---|
| Strong core work can still undersell itself if packaging is weak | Treat packaging as a milestone, not cleanup | The take-home explicitly evaluates repo quality, docs, and deployed access |
| Overexplaining can make the project feel defensive | Keep the write-up concise, honest, and decision-oriented | Reviewers want signal, not a wall of caveats |
| Deployed environments may behave differently from local runs | Smoke-test the deployed path before finalizing docs | Demo reliability is part of the product in this context |
| Production hardening could become a distraction | Document future concerns without implementing them now | This preserves credibility while respecting the exercise scope |

## Default Release Decisions
- Deployment target: use a single-container deployment on Render for the first public demo so OCR dependencies can run without serverless packaging constraints.
- Demo data: ship documented sample fixtures and matching expected values in the repo or a clearly labeled guided sample path in the app instead of building a separate sample-data mode.
- Walkthrough format: written walkthrough only for the required submission. Record a video only if all smoke tests are already green.
