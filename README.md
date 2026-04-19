# Alcohol Label Verifier

A deterministic, OCR-backed compliance checker for alcohol label submissions.
Reviewers upload a label image and the seven tracked application fields; the
verifier reads the label and returns a field-by-field verdict plus a
recommended action (`accept`, `manual_review`, or `request_better_image`).

## Scope

- **Beverage coverage:** distilled spirits only (bourbon, whiskey, tequila,
  gin, rum, vodka, scotch). Beer and wine are out of scope.
- **Flow:** single-label reviewer workbench. A batch surface exists in the
  repo but is not part of the reviewer-ready demo path.
- **Trust posture:** the verifier never auto-approves. Low OCR confidence or
  missing evidence returns `needs_review`, not a guess.

## Try the deployed demo

**https://ttbreader-production.up.railway.app**

Click a **Try a sample** card on the landing page — each runs the verifier
against a pre-loaded golden-set label. No upload, no account, no setup.

| Sample | Case | Expected verdict |
|---|---|---|
| Clean domestic match | `gs_001.png` | `match` |
| Import with country of origin | `gs_003.png` | `match` (import rule) |
| Needs review (occluded warning) | `gs_020.png` | `needs_review` |

The deployment uses this repo's Dockerfile, built on Railway's x86_64
infrastructure so PaddleOCR model weights are baked into the image at
build time rather than fetched at runtime.

## Run it locally (Docker)

```bash
docker build -t alc-levels .
docker run --rm -p 8000:8000 alc-levels
open http://localhost:8000
```

The Dockerfile targets `linux/amd64`. On x86_64 hosts (Railway, GitHub
Actions, any Linux CI), `docker build` bakes PaddleOCR weights into the
image and the running container never needs network for OCR models.

**On arm64 Macs,** QEMU emulation can choke on PaddleOCR's AVX2 path or
time out fetching weights from Baidu's CDN. Two options:

- Build on an x86_64 machine (Codespaces, cloud VM, CI) — recommended.
- Skip the bootstrap and accept a one-time runtime download:
  `docker build --build-arg ALLOW_MISSING_MODELS=true -t alc-levels .`

## Running the evals

The golden set is 28 synthetic labels: clean matches, normalization cases,
single-field mismatches, warning strictness, unreadable cases, and
import/domestic conditional rules.

```bash
# Harness smoke (reference target, mirrors expected outputs)
python3 evals/run_golden_set.py

# Against the real verifier
ALC_EVAL_TARGET=alc_label_verifier.adapter:target python3 evals/run_golden_set.py
```

Details and the dataset builder: [`evals/golden_set/README.md`](evals/golden_set/README.md).

## Smoke test

`scripts/smoke_test.sh` validates the full local surface and can be pointed
at a deployed URL for release checks.

```bash
# Local
bash scripts/smoke_test.sh

# Deployed
SMOKE_BASE_URL=https://<your-app>.up.railway.app bash scripts/smoke_test.sh
```

Checks: app boot, `GET /healthz`, one seeded sample via `POST /demo/gs_001`,
and the golden-set eval (local mode only).

## Approach and tradeoffs

See [`docs/approach.md`](docs/approach.md) for the design rationale: why
local-first OCR with deterministic validation, why `needs_review` is a
first-class verdict, and what is intentionally out of scope.

## Known limitations

- **OCR runtime:** PaddleOCR on CPU takes 2–5 seconds per label. No GPU path.
- **Beverage coverage:** non-distilled-spirit submissions are rejected.
- **Typography:** heavy stylization, glare, occlusion, or severe skew produce
  `needs_review` rather than a guess. By design.
- **No persistence:** uploaded images are processed in a temp file and
  deleted immediately. No database, no audit log.
- **No authentication:** the deployed demo is intentionally open.

## Privacy posture

- Uploaded images are streamed to a temp file, processed, and deleted at
  end-of-request. Not written to durable storage.
- No logging of uploaded content. Form values live in memory only.
- PaddleOCR runs fully locally — no label content leaves the container.
- Production-grade retention and auditing are out of scope for this prototype.

## Repository layout

```
alc_label_verifier/    # deterministic verifier (OCR + validation rules)
app/                   # FastAPI reviewer workbench
evals/golden_set/      # 28-case synthetic dataset + harness
docs/                  # approach note, plans, gap analyses
prds/                  # product requirement docs
tests/                 # pytest suite for verifier + web layer
scripts/               # smoke tests, model bootstrap, eval helpers
```

## Docs

- [Approach note](docs/approach.md)
- [PRDs](prds/)
- [Golden set README](evals/golden_set/README.md)
