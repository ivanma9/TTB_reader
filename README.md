# Alcohol Label Verifier

A deterministic, OCR-backed compliance checker for alcohol label submissions.
Reviewers upload a label image and the seven tracked application fields; the
verifier reads the label and returns a field-by-field verdict plus a
recommended action (`accept`, `manual_review`, or `request_better_image`).

---

## Quick start

Everything a reviewer needs to run the app, the evals, and the smoke test.

### 1. Try the hosted demo (fastest)

**https://ttbreader-production.up.railway.app**

No setup required. The deployment uses this repo's Dockerfile, built on
Railway's x86_64 infrastructure so PaddleOCR model weights are baked into
the image at build time.

### 2. Run the app locally (Docker)

```bash
docker build -t alc-levels .
docker run --rm -p 8000:8000 alc-levels
open http://localhost:8000
```

The Dockerfile targets `linux/amd64`. On x86_64 hosts (Codespaces, cloud
VMs, Linux CI), `docker build` bakes PaddleOCR weights into the image and
the running container never needs network for OCR models.

**On arm64 Macs,** QEMU emulation can choke on PaddleOCR's AVX2 path or
time out fetching weights from Baidu's CDN. Two options:

- Build on an x86_64 machine (Codespaces, cloud VM, CI) — recommended.
- Skip the bootstrap and accept a one-time runtime download:
  ```bash
  docker build --build-arg ALLOW_MISSING_MODELS=true -t alc-levels .
  ```

### 3. Run the evals

The golden set is 28 synthetic labels covering clean matches, normalization
cases, single-field mismatches, warning strictness, unreadable cases, and
import/domestic conditional rules.

```bash
# Harness smoke (reference target, mirrors expected outputs)
python3 evals/run_golden_set.py

# Against the real verifier
ALC_EVAL_TARGET=alc_label_verifier.adapter:target python3 evals/run_golden_set.py
```

Dataset builder + details: [`evals/golden_set/README.md`](evals/golden_set/README.md).

### 4. Smoke test

`scripts/smoke_test.sh` validates the full local surface and can also be
pointed at a deployed URL for release checks.

```bash
# Local
bash scripts/smoke_test.sh

# Deployed
SMOKE_BASE_URL=https://<your-app>.up.railway.app bash scripts/smoke_test.sh
```

Checks: app boot, `GET /healthz`, the queue flow (`GET /`, `GET /queue/gs_001`,
`POST /queue/gs_001/verify`, `POST /queue/gs_001/action`), `GET /test`, and the
golden-set eval (local mode only).

### 5. (Optional) Persist the queue across restarts

By default the queue is in-memory and resets on process restart. To persist
across restarts, set `QUEUE_PERSIST_PATH` to a writable JSON file path:

```bash
QUEUE_PERSIST_PATH=/data/queue.json uvicorn app.main:app
```

On Railway, pair this with a mounted volume so the file survives redeploys;
otherwise it lives in ephemeral container storage and is wiped per deploy.
If the file is missing at boot the queue re-seeds with the three defaults;
if it's malformed the app logs a warning and re-seeds rather than crashing.

---

## Scope

- **Beverage coverage:** distilled spirits only (bourbon, whiskey, tequila,
  gin, rum, vodka, scotch). Beer and wine are out of scope.
- **Flow:** single-reviewer queue — the landing page lists pre-paired
  application+label records awaiting verification. A secondary `/test`
  surface accepts arbitrary uploads for exploration; a `/batch` surface
  exists in the repo but is not part of the reviewer-ready demo path.
- **Trust posture:** the verifier never auto-approves. Low OCR confidence or
  missing evidence returns `needs_review`, not a guess.

---

## Demo walkthrough

The landing page is a **review queue** — three pre-paired application+label
records awaiting verification. For each one, a reviewer would:

1. Open the application from the queue.
2. Run verification — the verifier compares the label OCR against the
   application record.
3. Record an action: **Approve**, **Reject**, or **Request better image**.

The three seeded items:

| Application | Case | What it shows |
|---|---|---|
| `COLA-2026-0412-001` | Clean domestic match | Every field matches — expected verdict `match`, recommended action `Approve`. |
| `COLA-2026-0413-027` | Import with country of origin | Exercises the import conditional rule — expected verdict `match`. |
| `COLA-2026-0415-009` | Needs review (occluded warning) | OCR can't read the warning — expected verdict `needs_review`, recommended action `Request better image`. |

Status badges persist in memory for the life of the process; restarting the
app resets all items back to `Pending`.

### Simulate more submissions

To demo with more variety, click **+ Simulate submission** on the landing
page. Each click picks a random unqueued golden-set case (28 total) and
pushes it onto the queue with a fabricated COLA id and submitter. The
button disables itself once all 28 are queued. This is a demo affordance
only — in production, applications arrive from COLA upstream; reviewers
never create them.

### Bring-your-own label

For evaluators who want to poke the verifier at arbitrary inputs, the
**Test a label** tab (top nav) keeps the manual-entry form: upload any
label image and type the application values by hand.

In production, application fields would come from COLA — reviewers would
never type them. The `/test` surface exists only for exploration; it does
not add items to the queue.

---

## Approach, tools, assumptions

**Approach** — `docs/approach.md` covers the design rationale: why
local-first OCR with deterministic validation, why `needs_review` is a
first-class verdict, and what is intentionally out of scope.
`docs/tradeoffs.md` is a 18-decision breakdown (chosen / rejected / why /
what it costs us / what stays open), including the stakeholder asks from
the take-home brief and how each one was or wasn't addressed.

**Tools used**

- **Python 3.11** — runtime.
- **PaddleOCR PP-OCRv5 mobile** (CPU, local) — text extraction. Weights
  baked into the container at build time; no runtime model fetch in the
  happy path.
- **FastAPI 0.111+** + **Jinja2** — web layer (reviewer queue,
  `/test` surface, `/batch` surface).
- **rapidfuzz** — bounded fuzzy matching inside the deterministic
  validation rules.
- **pytest** — test suite (verifier + web).
- **Docker** (`linux/amd64`) — single-container deployment; Railway
  hosts the demo.

Everything runs locally inside the container. No hosted inference APIs,
no external model endpoints, no outbound network calls on the
verification path.

**Assumptions** — `presearch.md` captures the up-front options considered,
the locked Day-1 decisions, and the explicit **Assumptions** the prototype
is built on: manual application values (no COLA ingest), distilled-spirits
scope, user-supplied test labels, and evaluator tolerance for documented
limitations on advanced typography checks and image-quality extremes.

---

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

- [Approach note](docs/approach.md) — architecture, why queue-first, why
  `needs_review` is first-class
- [Tradeoffs](docs/tradeoffs.md) — 18 decisions with why / cost / what
  stays open
- [Presearch](presearch.md) — options considered, locked decisions,
  explicit assumptions
- [PRDs](prds/) — per-milestone product requirements
- [Golden set README](evals/golden_set/README.md) — eval dataset +
  harness
