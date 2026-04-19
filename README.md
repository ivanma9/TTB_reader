# Alcohol Label Verifier

A deterministic, OCR-backed compliance checker for alcohol label submissions.
Reviewers upload a label image and the seven tracked application fields; the
verifier reads the label and returns a field-by-field verdict plus a recommended
action (`accept`, `manual_review`, or `request_better_image`).

## Scope

- **Beverage coverage:** distilled spirits only (bourbon, whiskey, tequila,
  gin, rum, vodka, scotch). Beer and wine are explicitly out of scope for
  this MVP.
- **Flow:** single-label reviewer workbench first. A batch-review surface
  exists in the repo but is not part of the reviewer-ready demo path.
- **Trust posture:** the verifier never auto-approves. Low OCR confidence or
  missing evidence returns `needs_review`, not a guess.

## Deployed demo

A hosted version of the single-label workbench is available at:

> _Deployed URL will be added here once the final candidate is live._

To exercise it end-to-end in under two minutes, click one of the **Try a
sample** cards on the landing page — each runs the verifier against a
pre-loaded golden-set label with no upload required.

## Quick start (Docker)

The fastest way to try the app is the deployed demo URL above — no setup
required. If you want to run it locally with Docker, read the architecture
note below first.

```bash
# Build (Linux x86_64 hosts, or any CI: works out of the box)
docker build -t alc-levels .

# Run
docker run --rm -p 8000:8000 alc-levels

# Open in a browser
open http://localhost:8000
```

### Why x86_64 matters for the build

PaddleOCR model weights are fetched from Baidu's CDN (`bj.bcebos.com`)
during `docker build`. Once fetched, they are baked into the image, and
the running container never touches the network for OCR models again.
This gives an immutable, reproducible artifact — the image you test is
the image that runs in prod.

On x86_64 hosts (Render, GitHub Actions, most CI runners, Codespaces), this
just works. On arm64 Macs, two things can go wrong:

1. Docker uses QEMU to emulate x86_64, which can choke on Paddle's AVX2
   instructions during model init.
2. Some home networks route to Baidu's CDN slowly enough for Paddle's
   download to time out.

If the default build fails on an arm64 host, you have two options:

```bash
# (a) Build on a real x86_64 machine (Codespaces, a cloud VM, CI) — recommended.

# (b) Skip the build-time bootstrap and accept a one-time runtime download:
docker build --build-arg ALLOW_MISSING_MODELS=true -t alc-levels .
```

Option (b) produces a smaller image but requires Baidu CDN reachability
when you run the container for the first time — the exact failure mode
immutable builds are supposed to avoid. Use it only for local iteration.

## Local run (optional, Linux x86_64)

Native setup is supported only on Linux x86_64 because of the Paddle wheel
constraint. On macOS arm64 or Windows, use the Docker path above.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install ".[web,ocr]"
python scripts/bootstrap_models.py
uvicorn app.main:app --reload
```

## Running the evals

The golden set is 28 synthetic labels covering clean matches, normalization
cases, single-field mismatches, warning-strictness cases, unreadable-image
cases, and conditional (import/domestic) rules.

```bash
# Against the reference target (mirrors expected outputs — harness smoke test)
python3 evals/run_golden_set.py

# Against the real verifier
ALC_EVAL_TARGET=alc_label_verifier.adapter:target python3 evals/run_golden_set.py
```

Details and the dataset builder live in [`evals/golden_set/README.md`](evals/golden_set/README.md).

## The guided demo path

The landing page surfaces three curated samples:

| Sample | Case | What it shows |
|---|---|---|
| Clean domestic match | `gs_001.png` | Every field matches — expected verdict `match`. |
| Import with country of origin | `gs_003.png` | Exercises the import conditional rule. |
| Needs review (occluded warning) | `gs_020.png` | OCR can't read the warning — expected verdict `needs_review`. |

Clicking a sample runs the verifier against the pre-loaded image and renders
the field-by-field result. No upload needed. The form fields are also
prefilled so reviewers can see what was fed into the verifier.

## Smoke test

`scripts/smoke_test.sh` validates the full local surface and can be pointed at
a deployed URL for final release checks.

```bash
# Local
bash scripts/smoke_test.sh

# Deployed
SMOKE_BASE_URL=https://<your-app>.onrender.com bash scripts/smoke_test.sh
```

The script checks: app boot, `GET /healthz`, one seeded sample submission via
`POST /demo/gs_001`, and the golden-set eval run.

## Approach and tradeoffs

See [`docs/approach.md`](docs/approach.md) for a short tour of the design
decisions: why local-first OCR with deterministic validation, why
`needs_review` is a first-class verdict, and what is intentionally left out of
this prototype.

## Known limitations

- **OCR runtime.** PaddleOCR on CPU takes 2–5 seconds per label. No GPU path.
- **Beverage coverage.** Non-distilled-spirit submissions will be rejected.
- **Typography.** Heavy stylization, glare, occlusion, and severe skew will
  produce `needs_review` rather than a guess. This is by design.
- **No persistence.** Uploaded images are processed in a temp file and
  deleted immediately. No database, no audit log.
- **No authentication.** The deployed demo is intentionally open for reviewer
  access.

## Privacy posture

- Uploaded label images are streamed to a temp file, processed, and deleted
  at the end of the request. They are not written to durable storage.
- There is no logging of uploaded content. Application form values are kept
  in memory only for the duration of the request.
- PaddleOCR runs fully locally — no label content is sent to any third party.
- Production-grade retention, auditing, and compliance controls are
  explicitly out of scope for this prototype.

## Repository layout

```
alc_label_verifier/    # deterministic verifier (OCR + validation rules)
app/                   # FastAPI reviewer workbench
evals/golden_set/      # 28-case synthetic dataset + harness
docs/                  # approach note, PRDs, plans
tests/                 # pytest suite for verifier + web layer
scripts/               # smoke tests, model bootstrap, eval helpers
```

## Docs

- [Approach note](docs/approach.md)
- [PRDs](prds/)
- [Golden set README](evals/golden_set/README.md)
