# Tradeoffs

The reasoning behind the prototype's major decisions — what was chosen,
what was rejected, what it costs, and which stakeholder concerns or
research findings drove the call. Synthesized from
`docs/presearch.md`, `docs/approach.md`, `docs/m1-gaps.md`,
`docs/real-label-gaps.md`, and the plans under `docs/plans/`.

---

## 1. Local-first OCR over hosted multimodal APIs

**Chosen:** PaddleOCR PP-OCRv5 mobile models, CPU-only, cached weights,
running entirely inside the deployed container.

**Rejected:** a hosted multimodal model (Option A in presearch) for
extraction and validation; Tesseract as the local engine.

**Why:** the user context — TTB compliance reviewers on government
networks — makes outbound traffic to third-party inference endpoints a
real deployment risk (Marcus's firewall concern). A cloud-only pipeline
would also introduce variable latency, quota/credential failure modes,
and data-exit concerns for label images that may carry IP or commercial
sensitivity. Tesseract was tried in early exploration and underperformed
on decorative label typography, so Paddle was the compromise that kept
us local without accepting Tesseract's quality floor.

**What it costs us:** more engineering to get acceptable extraction on
messy photography; weaker headline performance on low-quality images
than a strong hosted VLM would give.

**What stays open:** the verifier is a pure function — the OCR backend
could be swapped, or a hybrid "low-confidence fallback to hosted model"
(Option C in presearch) added later, without touching the rule engine.

---

## 2. Fuzzy extraction separated from deterministic validation

**Chosen:** two concerns, two code paths.
1. **Extraction (fuzzy):** OCR reads pixels, surfaces per-detection
   confidence, refuses to commit when signal is weak.
2. **Validation (deterministic):** given extracted text + the
   application payload, rules decide `match` / `mismatch` /
   `needs_review`. Identical inputs produce identical verdicts,
   forever.

**Rejected:** a single LLM pass that both reads the label *and* renders
the compliance judgment.

**Why:** reviewers cannot trust a stochastic black box on a compliance
task. The split is also what lets the 28-case golden set act as a real
regression harness — if an OCR change moves behavior, the eval
pinpoints which cases moved and in which direction.

**What it costs us:** no semantic matching ("Kentucky Bourbon" ≠
"Kentucky Straight Bourbon Whiskey" as far as the verifier is
concerned). Over-matching would erode trust faster than under-matching,
so the conservative side won.

---

## 3. `needs_review` as a first-class verdict

**Chosen:** three verdicts — `match`, `mismatch`, `needs_review`.
`needs_review` maps to the reviewer action `request_better_image`. The
golden set deliberately includes cases that should land there (heavy
glare, partial occlusion, bottom-crop) so the path is tested, not just
documented.

**Rejected:** collapsing ambiguous cases into `mismatch`; binary
accept/reject.

**Why this matters for Jenny (Junior Compliance Agent):** she asked
whether the system could handle labels photographed at odd angles,
with glare, or in poor lighting, so agents wouldn't have to reject and
wait for a better image. Our answer is: the verifier refuses
gracefully. Silently "fixing" a hard-to-read label means the first time
the fix is wrong, an applicant gets an incorrect rejection — or worse,
an incorrect approval. The expected cost of a bad guess exceeds the
friction of asking for a better image. Jenny herself flagged
restoration as "maybe out of scope for a prototype," and keeping
`needs_review` distinct from `mismatch` is what preserves the honest
answer.

**What a production version would add:** pre-processing for mild skew
and low-contrast correction, region-of-interest detection so glare on
one section doesn't fail the whole label, and a visible confidence
indicator so reviewers can see *why* a field was accepted on a degraded
image.

---

## 4. Bounded fuzzy matching, no semantic matching

**Chosen:** normalize case, whitespace, and punctuation; tolerate small
OCR slip-ups via bounded fuzzy distances and targeted typo fixes (e.g.
`"m1"` → `"ml"`, word-form unit aliases like `"milliliters"` →
`"ml"`).

**Rejected:** synonym tables, semantic matching, or LLM "do these mean
the same thing?" calls.

**Already handled (from interviews):**
- **Brand variants** — "STONE'S THROW" vs "Stone's Throw" (Dave's ask)
  is handled by the normalization layer.
- **Warning strictness** — Jenny's strict treatment of the
  `GOVERNMENT WARNING:` statement is enforced as a dedicated field with
  its own rules; case-sensitive prefix cues are part of the match
  logic, not a generic fuzzy pass.

**What it costs us:** real labels that phrase the same concept
differently ("Product of Peru" vs "Country of Origin: Peru") require
explicit anchor broadening in the matcher rather than being handled by
magic. Category A of the real-label work did exactly that for
`country_of_origin`, `net_contents`, and `brand_name` — an engineering
cost we accept in exchange for determinism.

---

## 5. Strict validation of the government warning

**Chosen:** exact statement match after OCR cleanup that doesn't change
wording semantics; strict `GOVERNMENT WARNING:` prefix check; if
bold-typography validation can't be done reliably, mark it
`manual_review` rather than claim certainty.

**Rejected:** identical fuzzy tolerance across all fields; attempting
bold-text detection via rich document analysis.

**Why:** TTB treats the warning as exact-text-required. Tolerating
paraphrase would produce false negatives in a context where the
consequence is a public-facing compliance violation.

**What it costs us:** small-print OCR on real labels often lands 94–96
on the fuzzy scale — below the 97 threshold we picked — so many real
labels resolve to `needs_review` on the warning. `m1-gaps.md` tracks
this as a tuning target once a larger real-label corpus exists; the
answer is to improve OCR on small-print regions, not to loosen the
gate.

---

## 6. Distilled spirits only in the MVP

**Chosen:** implement distilled-spirits rules correctly; beer and wine
are future milestones with their own rule profiles and datasets.
Non-distilled submissions are rejected at the category check.

**Rejected:** a single "universal" checklist that pretends to cover all
three beverage categories.

**Why:** the labeling rules diverge materially across the three. Beer
and wine have different ABV thresholds (and in some cases no mandatory
ABV disclosure at all), distinct class/type vocabularies, different
conditional disclosures (sulfite declarations, allergen callouts), and
different government-warning placement rules. Three rule sets + three
golden-set corpora + three sets of edge cases means none of them gets
done well. One category done correctly is more useful as a reference
implementation than three done shallowly.

**What a production version would add:** category-specific rule
modules (`matching_wine.py`, `matching_beer.py`) behind the same
verifier contract, with the category field routing at verify time. The
existing matcher architecture is designed to accommodate this without
rewriting the framework.

---

## 7. Peak-season batch deferred (Sarah's ask)

**Asked for (Sarah, Deputy Director):** handling 200–300 label
applications dumped at once during peak season, instead of processing
them one at a time.

**What shipped:** a lightweight `/batch` surface capped at ~10 labels
per session, processed one row at a time. The reviewer-ready demo path
is the single-label queue.

**Why:** hitting Sarah's real volume means concurrent OCR workers,
partial-failure triage, a progress/status UI that stays legible at 200+
rows, and a way to route exceptional cases back to the single-label
review without losing batch context. That's meaningful work — enough
to dilute the polish on the single-label queue flow (PRD 02, the core
of the take-home). The batch surface exists as a credible placeholder,
not a reviewer-ready flow.

**What a production version would add:** a real job queue (not
in-process), per-label progress indicators, a triage view that surfaces
`needs_review` / `mismatch` rows first, bulk expected-data entry (CSV
import), and retry/requeue for transient OCR failures.

---

## 8. Batch processing: visible sequential queue, no background worker

**Chosen:** `/batch` stages uploaded files once to a temp batch
directory, keeps batch metadata in a process-local store, and processes
exactly **one** row per `POST /batch/{batch_id}/process-next` call. The
browser drives progression.

**Rejected:** (a) one long blocking request that processes the whole
batch, (b) a background worker or task queue.

**Why:** a visible sequential queue is easier to reason about and
easier to demo. No hidden threads; no inter-request state juggling
beyond the batch-id dict; reviewer sees progress land row-by-row. The
process-local store is explicitly scoped as "acceptable for the local
beta and take-home demo, not intended as a production multi-worker
design."

**What it costs us:** no cross-process batch durability. No parallel
row processing — the bound is OCR latency × row count. At the enforced
≤10-row cap this is still inside the demo budget.

---

## 9. Batch limits and the `processing_error` state

**Chosen:** enforce at stage time — ≤10 files per batch, ≤20 MB per
file, ≤100 MB total. Represent unexpected row-processing failures as a
distinct `processing_error` state, rolled up under the batch
`needs_review` count but surfaced separately in the UI.

**Rejected:** letting unexpected failures masquerade as field-level
`unreadable`.

**Why:** a system error is not a label-quality problem. Conflating the
two would misdirect the reviewer ("request a better image" when the
real answer is "retry later").

---

## 10. Queue-first landing over a manual-entry form

**Chosen:** `GET /` renders a pre-paired application+label work queue.
The original manual-entry form moved verbatim to `/test` as a secondary
"bring-your-own label" surface for evaluators.

**Rejected:** keeping the single-form workbench with demo cards as the
primary surface.

**Why:** the three reviewer interviews (Sarah, Dave, Jenny) all
described the same flow — open an *existing* application, see the
*already-populated* fields next to the label, record a decision.
Reviewers never type the application values themselves; those come from
the applicant upstream via COLA. The old landing put the reviewer in
the wrong role.

**What it costs us:** two surfaces to maintain instead of one; `/test`
is explicitly secondary, not a reviewer workflow. The verifier itself
is untouched — this is a UX decision, not a data-model change.

---

## 11. "Simulate submission" as an explicit demo affordance

**Chosen:** a button on the queue landing that picks an unqueued case
from the 28-entry golden-set pool, fabricates a COLA ID and submitter
using mechanical rules, and appends it to the queue. Disables itself
when the pool is exhausted; the POST endpoint also returns 409 as
defence against concurrent clicks.

**Rejected:** (a) restricting the demo to the three seeded items,
(b) building a generic "any upload becomes a queue item" channel that
pretends to be COLA ingest.

**Why:** three fixed items don't demo at scale; a fake COLA ingest
would blur the line between demo affordance and production pretension.
The pool is labeled clearly so evaluators understand the intent —
upstream submission is a COLA concern, not a reviewer concern.

**What it costs us:** queue IDs reuse the golden-set `case_id`, so the
same pool entry can only be added once (by construction). Submitter
derivation is mechanical (`titlecase(brand) + " LLC"` domestic,
`+ " Imports"` import) — realistic enough for demo, not authoritative.

---

## 12. Opt-in persistence via `QUEUE_PERSIST_PATH`

**Chosen:** queue state is in-memory by default. Setting
`QUEUE_PERSIST_PATH` to a writable JSON path turns on atomic load-on-
startup + rewrite-on-mutation.

**Rejected:** requiring persistence for all deployments; using a
database.

**Why:** the prototype's default posture is "no storage of uploaded
artifacts, no cross-request state." Persistence is useful for the
Railway demo so reviewers don't lose progress on redeploy, but it's
not load-bearing for the core experience. JSON + `os.replace` is
enough — a database is overkill for ≤28 items.

**What it costs us:** the persist file must survive process restarts,
which on Railway means mounting a volume at that path. Documented,
not required.

---

## 13. Synthetic golden set first, real-label corrections second

**Chosen:** a hand-crafted 28-case synthetic set
(`evals/golden_set/`) that covers every branch of the validation logic
and every degradation class the OCR should refuse. A separate
`docs/real-label-gaps.csv` + `evals/real_labels/corrections.jsonl`
captures where real labels diverge from the synthetic fixtures.

**Rejected:** bootstrapping the eval directly on scraped real labels.

**Why:** real labels are expensive to hand-label, carry IP risk, and
their "truth" fields in public datasets are often structurally wrong
for our purpose. The COLA CSV's `APPLICANT_NAME` is the permit holder,
not the bottler on the label; `CLASS_NAME` is a normalized TTB class
code, not the fanciful class text shown to consumers. Scoring against
those as-is would blame the verifier for a data-source mismatch.

**What it costs us:** the synthetic set passed 100% on every gate but
the real-label run initially came back at `0 / 17% / 0 / 42%` on the
four accuracy metrics. That gap was real and worth surfacing — the
Category A / B / C plans exist specifically to close it. Category A
moved `brand_name` 7→22, `net_contents` 0→22, and
`country_of_origin` 1→3 imports in a single pass. Category B adds
optional back-label OCR. Category C hand-labels the two fields the
public CSV truth can't support.

---

## 14. Front + back label contract (Category B)

**Chosen:** the verifier accepts an optional `back_image_path`; when
provided, back-label OCR lines are **concatenated** after front lines
with no side tagging or resorting.

**Rejected:** side-aware matchers that know which panel each line came
from.

**Why:** `partition_lines` already scans sequentially for the
`"GOVERNMENT WARNING"` prefix. Appending back lines routes the warning
into the correct bucket without touching partitioning or any individual
matcher. Minimum-surface change, maximum payoff on the warning field
(which is 39/43 `unreadable` on a front-only feed because the warning
lives on the back panel).

**What it costs us:** matchers lose the ability to prefer front-label
evidence over back-label evidence. Acceptable now — no current matcher
would use that signal. Revisit if a future rule needs it.

---

## 15. Confidence thresholds as asymmetric knobs

**Chosen:** `0.80` minimum confidence for standard field mismatches;
`0.90` for government-warning mismatches. Below threshold routes to
`needs_review`.

**Rejected:** a single universal confidence bar.

**Why:** the warning has zero tolerance for wrong text, so the cost of
a false `mismatch` there is higher than for a brand name. Asymmetric
thresholds reflect asymmetric stakes.

**What it costs us:** two numbers to tune, not one. `m1-gaps.md` flags
warning-body fuzzy scores landing in the 94–96 band on real small-print
OCR — expect to revisit once a larger real-label corpus exists.

---

## 16. Sub-5-second latency target

**Asked for:** Sarah raised the prior scanning vendor's slowness as a
failure mode to avoid. Presearch locked ≤5 seconds as the target.

**What shipped:** typical verification lands at 2–5s on CPU PaddleOCR,
inside the target. Longer labels can push this.

**Why not a GPU path:** would close the remaining gap, but it's out of
scope for a local-first prototype running in a single container.
Documented as future work, not a shipping constraint.

---

## 17. Privacy posture

**Chosen:**
- Uploaded images are streamed to a temp file, processed, deleted at
  end-of-request.
- No content logging.
- OCR runs fully locally — nothing leaves the container.

**Rejected:** durable audit logs, content-indexed search, any form of
PII-touching retention.

**Why this matters for Marcus (compliance):** his concern was
retention and exfiltration. The posture above makes both moot for the
prototype. Production hardening (durable audit, retention policy,
access controls, PII handling, FedRAMP-style deployment constraints) is
acknowledged in writing and explicitly deferred.

---

## 18. What is intentionally not production-ready

Called out so reviewers don't mistake the omission for an oversight.

- **No auth, no access control.** The deployed demo is open by
  design.
- **No durable audit log.** Uploads are processed and discarded.
- **No observability beyond smoke checks.** Real production would want
  structured logging, per-field confidence histograms, and drift
  monitoring on the golden set.
- **No human feedback loop.** A real deployment would let reviewers
  correct the verifier and feed those corrections back into rule
  tuning.
- **Single-region, single-host.** No horizontal scaling, no queue
  infrastructure.
- **No COLA integration.** Applications enter the queue via seed +
  simulate; in production they would flow from upstream ingest.

Each is a deliberate scope cut. The submission is a prototype
demonstrating the verification approach, not a production deployment.

---

## Source documents

- `docs/presearch.md` — problem framing, constraints, options considered,
  Day-1 locked decisions
- `docs/approach.md` — current architecture narrative, queue-first
  rationale, explicit non-goals
- `docs/m1-gaps.md` — fuzzy-threshold calibration notes on the
  synthetic gate
- `docs/real-label-gaps.md` — synthetic-vs-real accuracy gap + per-field
  failure modes that drove Categories A / B / C
- `docs/plans/2026-04-16-m2-single-label-reviewer.md` — single-label
  workbench scope
- `docs/plans/2026-04-16-m3-batch-review-beta.md` — batch workflow
  scope and locked beta decisions
- `docs/plans/2026-04-16-m4-submission-and-reviewer-readiness.md` —
  deployment + submission packaging
- `docs/plans/2026-04-17-real-label-category-a.md` — matcher fixes for
  `net_contents`, `brand_name`, `country_of_origin`
- `docs/plans/2026-04-17-real-label-category-b.md` — front+back image
  contract
- `docs/plans/2026-04-17-real-label-category-c.md` — hand-labeled
  class/producer truth
- `docs/plans/2026-04-19-reviewer-queue-landing.md` — queue-first UX
- `docs/plans/2026-04-19-simulate-cola-submission.md` — simulate
  affordance and opt-in persistence
