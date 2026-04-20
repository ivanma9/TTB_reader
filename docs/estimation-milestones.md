# Estimation and Milestones

## Estimation Assumptions
- Team size and roles: 1 product-minded full-stack engineer owning OCR evaluation, app implementation, deployment, and docs.
- Velocity assumptions: 5 to 6 focused implementation days for a strong take-home submission, assuming existing eval assets remain usable.
- Known dependencies: local OCR stack selection, image preprocessing quality, simple deploy target, and a stable output contract compatible with the golden-set harness.
- Risk buffer: reserve the final day for polish, bug fixes, deployment issues, and documentation; do not spend that buffer on new core features.

## Work Breakdown Structure
| Epic | Task | Owner Role | Effort (days) | Planned Day(s) | Dependencies |
|---|---|---|---|---|---|
| Verification engine foundation | Lock OCR stack, preprocessing baseline, and confidence thresholds | Full-stack engineer | 0.5 | Day 1 AM | Existing eval fixtures and sample labels |
| Verification engine foundation | Implement distilled-spirits rule profile and output contract skeleton | Full-stack engineer | 0.5 | Day 1 PM | OCR extraction baseline |
| Verification engine foundation | Wire the verifier into `evals/run_golden_set.py`, fix failures, and record runtime baseline | Full-stack engineer | 1.0 | Day 2 | Rule engine implementation |
| Reviewer MVP | Build single-label upload plus expected-data form | Full-stack engineer | 0.5 | Day 3 AM | Stable verifier interface |
| Reviewer MVP | Design field-by-field result view with match, mismatch, and needs-review states | Full-stack engineer | 0.75 | Day 3 PM to Day 4 AM | Stable verifier interface |
| Reviewer MVP | Add unreadable-image fallback, recommended actions, and self-run walkthrough timing | Full-stack engineer | 0.25 | Day 4 AM | Result model defined |
| Reviewer MVP | Polish happy-path usability and final MVP acceptance checks | Full-stack engineer | 0.5 | Day 4 PM | Prior MVP tasks complete |
| Batch beta | Add multi-file intake and sequential queue processing | Full-stack engineer | 0.5 | Day 5 AM, conditional | Stable single-label workflow |
| Batch beta | Add batch summary table and per-label drill-down | Full-stack engineer | 0.5 | Day 5 PM, conditional | Queue processing |
| Submission readiness | Deploy app and validate demo environment | Full-stack engineer | 0.5 | Day 6 AM | Stable MVP build |
| Submission readiness | Write README, approach notes, and known tradeoffs | Full-stack engineer | 0.25 | Day 6 midday | Finalized scope decisions |
| Submission readiness | Run final smoke test across golden set, local app, and deployed demo | Full-stack engineer | 0.25 | Day 6 PM | Deployment plus docs complete |

## Milestones
| Milestone | Target Date | Exit Criteria | Blocking Dependencies |
|---|---|---|---|
| M1: Verification engine foundation | Day 1-2 | Golden-set harness runs against a real verifier; output contract is complete; MVP metric gates are met or clearly tracked with a short gap list | OCR selection, rules model |
| M2: Single-label reviewer MVP | Day 3-4 | Reviewer can upload one label, enter expected distilled-spirits fields, and receive a clear result in about 5 seconds or less | M1 complete |
| M3: Batch review beta | Day 5 | User can review up to 10 labels in one session with per-label status and drill-down details, without destabilizing the single-label path | M2 stable |
| M4: Submission and reviewer readiness | Day 6 | Deployed URL, runnable repo, README, approach docs, and demo-ready sample flow are all complete | M2 complete; M3 if retained |

## Day-by-Day Execution Plan
| Day | Focus | Exit Condition |
|---|---|---|
| Day 1 | Lock PaddleOCR stack, preprocessing baseline, confidence thresholds, and verifier contract | No blocking implementation questions remain for the engine path |
| Day 2 | Complete verifier implementation and pass or nearly pass the golden-set gates with a short gap list | Engine is stable enough for UI integration |
| Day 3 | Build the single-label input workflow and connect it to the real verifier | Happy path works end to end locally |
| Day 4 | Finish result presentation, unreadable fallbacks, and usability polish | Single-label MVP is demoable and measurable |
| Day 5 | Add batch only if Day 4 MVP is stable; otherwise spend the day on polish, bugs, and deployment prep | Batch is either complete or formally cut without harming M2 |
| Day 6 | Deploy, document, run smoke tests, and package the submission | Reviewer-ready final candidate is complete |

## Critical Path
1. Choose a local-first verification approach and make it pass the existing distilled-spirits eval gates.
2. Ship the single-label reviewer flow on top of that engine with a crisp human-in-the-loop UX.
3. Package the project for review with deployment, docs, and a reliable demo path.

## Delivery Risks
| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| OCR quality struggles on stylized or low-quality labels | Medium | High | Lock the MVP to distilled spirits, preprocess aggressively, and prefer `needs_review` over false confidence |
| Batch mode consumes time needed for core demo stability | High | High | Treat M3 as conditional on M2 being stable; cut or simplify batch before compromising the main flow |
| Deployment differs from local behavior | Medium | Medium | Choose a minimal deployment surface, smoke-test the deployed app early, and avoid cloud-only OCR dependencies |
| Docs and evaluator packaging get left to the end | Medium | High | Keep `README`, approach notes, and demo scripts as first-class scope items and reserve final-day buffer for them |
| Overbuilding beverage coverage slows delivery | Medium | High | Keep the rule system extensible, but explicitly support distilled spirits only in the MVP |
