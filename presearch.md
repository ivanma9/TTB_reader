# Presearch

## Problem Statement
- Build a standalone proof-of-concept application that helps compliance agents verify alcohol label images against expected application data.
- The primary users are TTB label compliance agents with mixed technical comfort levels, plus reviewers evaluating the prototype.
- The opportunity is to reduce repetitive manual comparison work while preserving reviewer judgment for nuanced cases.
- The prototype should demonstrate that label verification can be faster, easier, and more consistent than the current manual workflow without requiring direct integration with the legacy COLA system.

## Constraints
- Technical:
  - The solution should operate as a standalone prototype with no direct COLA integration.
  - Processing time should target about 5 seconds or less per label to avoid repeating the failure of the prior scanning pilot.
  - The app must support common alcohol label fields including brand name, class/type, alcohol content, net contents, bottler/producer information, country of origin for imports, and the government warning statement.
  - The app should distinguish between fields that can tolerate normalization or fuzzy matching and fields that require exact validation.
  - MVP scope should be explicit about beverage-specific rules. The recommended MVP is to fully support distilled spirits labels first, using the sample label in the prompt as the reference path, while designing the rules engine so beer and wine variants can be added later.
  - Validation rules should be conditional where the prompt implies conditionality, such as country of origin only for imports and alcohol content rules varying by beverage type.
  - Government networks may block outbound traffic to many third-party domains, so dependence on cloud-only OCR or ML APIs is risky.
  - The repository currently has no existing application code, so implementation choices are unconstrained by prior architecture.
- Business:
  - This is a take-home prototype, not a production procurement deliverable.
  - Reviewers want evidence of sound engineering, sensible scope choices, and clarity of trade-offs.
  - A working core experience is more valuable than an ambitious but incomplete system.
  - Batch handling is an important stakeholder request and a strong differentiator if included in MVP or near-MVP scope.
  - The final submission must include a source repository, a README with setup and run instructions, brief documentation of approach/tools/assumptions, and a deployed application URL.
- Timeline:
  - The document explicitly frames the work as time-constrained.
  - The plan should prioritize a polished happy path for single-label verification before expanding into advanced robustness features.
- Compliance/Security:
  - Production-grade federal compliance is not required for this exercise.
  - The prototype should still avoid unnecessary storage of uploaded artifacts or external transmission of label images where possible.
  - The write-up should acknowledge future concerns such as PII handling, retention, and FedRAMP-style deployment constraints without overengineering for them now.

## Requirements Interpreted
- Core user flow:
  - Input a label image and expected application data.
  - Extract visible text from the label.
  - Compare extracted values against expected values.
  - Return a clear pass, fail, or needs-review style result with field-by-field reasoning.
- Scope model:
  - MVP should explicitly target distilled spirits labels first rather than pretending to fully implement every beer, wine, and spirits rule variant.
  - The validation design should still account for future beverage-specific rule profiles so the prototype does not hard-code one universal checklist.
  - Country of origin should be checked only when the product is marked or inferred as an import.
- Accuracy expectations:
  - Support tolerant comparison for values like brand name casing and punctuation when the meaning is obviously unchanged.
  - Support strict comparison for the government warning statement, including exact wording and a check for the `GOVERNMENT WARNING:` prefix formatting expectation where feasible.
  - Avoid converting low-confidence OCR output into false mismatches. If required text cannot be read reliably, the system should return `Needs review` or `Request better image`.
- UX expectations:
  - Clean, obvious interface with minimal navigation.
  - Reviewer should not need to understand OCR internals.
  - Mismatches should be visible immediately and easy to interpret.
  - Unreadable-image cases should have a clear fallback outcome and explanation instead of failing silently.
- Performance expectations:
  - Fast enough to fit inside an agent’s working rhythm.
  - Avoid long asynchronous waiting states for routine single-label checks.
- Nice-to-have signals:
  - Batch upload for importers submitting many labels at once.
  - Better preprocessing for imperfect label photography such as skew, glare, or low contrast beyond the minimum fallback behavior.

## Options Considered

### Option A: Cloud multimodal model API for extraction and validation
- Summary:
  - Send label images and expected fields to a hosted multimodal model for text extraction and comparison.
- Pros:
  - Fastest path to a polished demo with strong extraction on messy images.
  - Lower local implementation complexity.
  - Easier to add nuanced reasoning in mismatch explanations.
- Cons:
  - High risk if outbound traffic is blocked in the target environment.
  - Harder to justify for a government-adjacent proof of concept focused on future deployability.
  - Performance may vary based on network and provider latency.
- Risks:
  - Demo fragility if credentials, quotas, or network access fail.
  - Reviewers may see it as overly dependent on external services.

### Option B: Local-first OCR plus deterministic validation rules
- Summary:
  - Use local OCR to extract text from labels, then run rule-based normalization and field-specific comparison logic in the app.
- Pros:
  - Best fit for the stated network restrictions and standalone prototype framing.
  - Easier to explain and defend technically.
  - Predictable latency and no dependency on external inference endpoints.
  - Encourages explicit treatment of exact-match versus fuzzy-match fields.
- Cons:
  - More engineering work is required to handle messy images and layout variability.
  - OCR quality may be weaker than strong hosted multimodal services on difficult photos.
  - Warning-format checks like bold text may be difficult unless using richer document analysis.
- Risks:
  - OCR quality could drag down perceived intelligence if preprocessing is weak.
  - Edge cases in label layouts may require manual review fallback.

### Option C: Hybrid local-first pipeline with optional AI fallback
- Summary:
  - Default to local OCR and deterministic checks, with an optional hosted AI assist mode used only when extraction confidence is low.
- Pros:
  - Balances deployability with stronger performance on hard labels.
  - Gives a clear future roadmap from prototype to more advanced capability.
  - Lets the product degrade gracefully if network access is unavailable.
- Cons:
  - More architectural and UX complexity than a strict MVP needs.
  - Harder to fully implement in a time-constrained take-home.
  - Requires careful explanation of when fallback is invoked.
- Risks:
  - Could dilute focus and leave both the local and fallback paths underdeveloped.
  - Adds complexity before the base reviewer experience is proven.

## Decision Log
| Decision | Selected Option | Alternatives Rejected | Reason |
|---|---|---|---|
| Prototype architecture should be standalone and local-first | Option B | A, C | Best fit for stated network restrictions, standalone scope, and explainability |
| Core validation should separate exact-match and normalized-match rules by field | Custom rule set on top of Option B | Pure exact match, fully LLM-based reasoning | Matches stakeholder nuance around obvious equivalence versus mandatory exact text |
| MVP should optimize for single-label review first | Single-label workflow first, batch second | Batch-first build | Reduces delivery risk and aligns with “working core over ambitious incomplete features” |
| MVP should explicitly scope beverage rules | Distilled spirits first, extensible rule profiles later | Pretend full cross-category support in v1 | Matches the sample prompt, reduces implementation risk, and avoids incorrect universal validation logic |
| The system should surface `needs review` outcomes rather than binary automation | Human-in-the-loop result model | Fully automatic pass/fail | Reflects Dave’s feedback that judgment is still necessary in nuanced cases |
| External services should be optional or absent in the main demo path | No required cloud dependency | Cloud-required architecture | Keeps the prototype credible under blocked-network constraints |
| Submission requirements should be treated as first-class scope items | Plan for repo, README, approach notes, and deployed demo from the start | Treat packaging as end-stage cleanup | These are explicitly evaluated deliverables, not optional polish |

## Recommended MVP Direction
- Build a single-page or low-navigation web app optimized for one reviewer task: upload label, provide expected fields, run verification, inspect results.
- Scope the primary demo flow to distilled spirits labels, since the prompt provides a distilled spirits example and the take-home is explicitly time-constrained.
- Use a local OCR engine plus image preprocessing to extract text quickly.
- Structure validation as field rules plus conditional applicability rules:
  - Brand name, class/type, net contents, and government warning apply in the distilled spirits MVP flow
  - Alcohol content rules should be attached to beverage type rather than assumed universal
  - Country of origin should be checked only for import cases
- Normalize text for tolerant fields:
  - Case folding
  - Whitespace normalization
  - Smart punctuation normalization
  - Optional token similarity thresholds for brand and class/type
- Keep strict validation for the government warning text:
  - Exact statement match after OCR cleanup rules that do not change wording semantics
  - Explicit check that the prefix is `GOVERNMENT WARNING:`
  - If formatting like bold cannot be validated reliably, mark it as `manual review required` instead of claiming certainty
- Return field-by-field results with one of:
  - Match
  - Mismatch
  - Needs review
- When image quality or OCR confidence is too low for reliable validation, return `Needs review` or `Request better image` rather than a hard mismatch.
- Add batch upload only if the single-label path is already stable, fast, and easy to demo.

## Submission Requirements
- Source code repository with all application code.
- README with setup, local run, and deployed-demo instructions.
- Brief documentation covering approach, tools used, assumptions made, and known trade-offs.
- Deployed application URL that reviewers can access and test.
- Test data or sample labels sufficient to demonstrate the core verification flow.

## Validation Plan
- Validate feasibility first by testing OCR on 5 to 10 representative sample labels with varying layouts.
- Measure end-to-end latency from upload to displayed result, targeting under 5 seconds for routine cases on local hardware.
- Validate the distilled spirits MVP path end-to-end before expanding any broader beverage coverage.
- Test strict warning validation with:
  - Correct standard text
  - Casing errors in `GOVERNMENT WARNING:`
  - Minor wording deviations
  - Partial or occluded warning text
- Test fuzzy comparison with examples like:
  - `STONE'S THROW` vs `Stone's Throw`
  - Minor spacing and punctuation differences
  - Numeric formatting variants for alcohol content
- Validate UX by ensuring the entire workflow is understandable without documentation:
  - One primary action
  - Immediate visual result state
  - Clear explanation of why a field failed or needs review
  - Clear fallback when the image is unreadable or OCR confidence is too low
- Validate submission completeness before handoff:
  - Repo is organized and runnable
  - README covers setup and usage
  - Approach and assumptions are documented
  - Deployed URL works for external reviewers

## Assumptions
- The prototype can require users to enter or paste expected application values manually rather than importing them from COLA.
- Only a subset of full TTB rules needs to be implemented as long as the MVP scope is stated clearly. The recommended subset is distilled spirits-first with an extensible rules model.
- The evaluation audience will accept a prototype that clearly documents limitations around advanced typography checks and image-quality extremes.
- Sample labels can be user-supplied, sourced, or generated for testing during development.

## Execution Decisions Locked For Day 1
- Local OCR stack: use PaddleOCR PP-OCRv5 mobile models locally with cached weights and orientation classification enabled. Do not require cloud OCR in the main path.
- Warning formatting: validate warning wording and the `GOVERNMENT WARNING:` prefix strictly, but defer bold-style certainty to manual review.
- Batch mode: if batch is implemented, use a sequential queue-based workflow in MVP rather than concurrent workers.
- Beverage scope: make the MVP explicitly distilled spirits only. Do not attempt beverage-type inference in v1.
- Confidence threshold: use `0.80` as the initial minimum confidence for standard field mismatches and `0.90` for government warning mismatches; below threshold routes to `needs review`.

## Remaining Non-Blocking Follow-ups
- Add document unwarping only if Day 1 and Day 2 eval failures show skew or geometry is a dominant failure mode.
- Revisit import or export conveniences only if the single-label MVP and submission package are already stable.
