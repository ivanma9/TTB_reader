# Approach Notes

A short tour of the decisions behind this prototype. For full product
scoping, see the PRDs in [`prds/`](../prds/).

## Architecture at a glance

```
┌─────────────┐      ┌──────────────┐      ┌──────────────────┐
│ FastAPI UI  │ ───▶ │ verify_label │ ───▶ │ PaddleOCR + rules│
│ (app/)      │      │ (service.py) │      │ (matching.py)    │
└─────────────┘      └──────────────┘      └──────────────────┘
```

- **Web layer** (`app/`): FastAPI + Jinja templates. One request per
  verification. No persistence, no sessions, no auth.
- **Verifier** (`alc_label_verifier/`): pure function taking an image path
  and an application payload, returning a structured verdict. No web
  coupling. This is what the eval harness calls directly.
- **OCR** (`alc_label_verifier/ocr.py`): PaddleOCR 2.x, CPU-only, wrapped to
  surface low-confidence detections as `needs_review` rather than forcing
  a string.

## Why local-first OCR and deterministic validation

**Reviewers cannot trust a stochastic black box for a compliance task.** The
design separates two concerns:

1. **Extraction** (fuzzy): OCR reads pixels. Results come with per-detection
   confidence scores. When the signal is weak, the verifier returns
   `needs_review` instead of guessing.
2. **Validation** (deterministic): given extracted text and the application
   payload, rules decide match / mismatch / needs_review. Identical inputs
   produce identical outputs — same run, same verdict, forever.

This split is what lets the 28-case golden set act as a real regression
harness. If an OCR improvement changes behavior, the eval output tells us
exactly which cases moved and in which direction.

## Why `needs_review` is a first-class verdict

Compliance review has three real outcomes, not two:

- **`match`** → accept the submission
- **`mismatch`** → flag a specific field problem for manual review
- **`needs_review`** → the verifier cannot see clearly enough to call it

Collapsing `needs_review` into `mismatch` would erode reviewer trust the
first time a glare-covered label was silently flagged as "wrong brand
name." Keeping it separate lets the UI say the honest thing:
"request a better image."

The golden set deliberately includes cases that should land in
`needs_review` (heavy glare, partial occlusion, bottom-crop) so this path
is tested, not just documented.

## Why distilled spirits only

TTB labeling rules for beer and wine differ materially (ABV thresholds,
allowed class/type vocabularies, additional disclosures). Supporting all
three would mean three rule sets and three validation corpora. This
prototype picks one beverage category and does it correctly rather than
all three shallowly. Expanding coverage is a future milestone with its own
dataset.

## What is intentionally not production-ready

- **No auth / no access control.** The deployed demo is open for reviewer
  convenience.
- **No persistence.** Uploads are processed and discarded. No audit log.
- **No observability beyond smoke checks.** Real production would want
  structured logging, per-field confidence histograms, and drift monitoring
  on the golden set.
- **No human feedback loop.** A real deployment would let reviewers correct
  the verifier and flow those corrections back into rule tuning.
- **Single-region, single-host.** No horizontal scaling, no queueing.

## Tradeoffs considered

- **PaddleOCR vs. Tesseract vs. a hosted VLM.** Paddle was chosen for the
  balance of accuracy on stylized label typography and local-only
  execution. Tesseract underperformed on decorative typefaces in early
  tests. A hosted VLM would remove the local OCR headache but introduce
  data-exit concerns and unpredictable latency.
- **Fuzzy matching scope.** The verifier normalizes case, whitespace, and
  punctuation, and tolerates small OCR slip-ups via bounded fuzzy
  distances. It does **not** attempt semantic matching — "Kentucky
  Bourbon" is not treated as equivalent to "Kentucky Straight Bourbon
  Whiskey." Over-matching here would erode trust faster than
  under-matching.
- **Synthetic golden set.** Real labels are expensive to hand-label and
  carry IP risk. The 28-case synthetic set covers every branch of the
  validation logic and every degradation class the OCR should refuse.
  A real-label corrections file (`docs/real-label-gaps.csv`) tracks where
  real-world labels diverged from the synthetic set.

## Privacy posture

- Uploaded images are streamed to a temp file, processed, and deleted at
  the end of the request.
- No content logging.
- OCR runs fully locally — nothing leaves the container.
- Production hardening (durable audit, retention policy, access controls)
  is explicitly deferred.
