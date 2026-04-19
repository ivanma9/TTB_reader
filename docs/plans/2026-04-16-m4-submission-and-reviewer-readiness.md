# M4 Submission and Reviewer Readiness — Implementation Plan

**Goal:** Turn the current verifier repository into a reviewer-ready submission with a deployed single-label demo, a reproducible local run path, guided sample data, concise approach notes, and repeatable smoke checks.

**Scope lock:** M4 packages the single-label MVP for review. It may include the minimum missing work needed to make the single-label flow runnable and deployable, but it must not expand beverage scope, reopen verifier semantics, or depend on batch review shipping.

## Current Repo Reality
- The verifier, eval harness, and golden-set fixtures already exist.
- `app/` is effectively empty, so the reviewer-facing web surface is not yet implemented in the repo.
- `README.md` is missing at the repo root.
- `scripts/smoke_test.sh` does not exist yet.
- The current [Dockerfile](/Users/ivanma/Desktop/gauntlet/alc_levels/Dockerfile) still launches the eval runner instead of a web server.
- The OCR dependency path is container-friendly but not truly native cross-platform; `pyproject.toml` already notes Linux x86_64 constraints for Paddle wheels.

## Locked Decisions
- Reviewer flow: single-label only. Batch stays out unless it is already complete and stable before M4 work begins.
- Deployment target: single-container Railway deployment using the Dockerfile.
- Local setup posture: Docker-first quick start for reliable reproduction; native setup is secondary and documented only where it is actually supported.
- Demo data source: reuse curated golden-set fixtures and their matching application payloads instead of inventing a separate demo-only dataset.
- Smoke-test boundary: automate service health, seeded sample submission, eval harness, and deployed availability; keep README dry run as a separate manual release gate.

## Deliverables
1. A deployable web app for the single-label reviewer flow.
2. A root `README.md` with Docker-first quick start, local run, eval run, and deployed-demo instructions.
3. A short approach note in `docs/approach.md` covering architecture, tradeoffs, scope limits, and privacy posture.
4. Guided sample fixtures with matching expected values surfaced in the app or documented in the repo.
5. `scripts/smoke_test.sh` for local and deployed smoke validation.
6. Deployment configuration updates needed for Railway and container startup.

## Architecture for M4
- FastAPI remains the web layer because `pyproject.toml` already includes the `web` optional dependencies.
- The web app calls the existing `alc_label_verifier.service.verify_label` entrypoint directly. The eval harness contract remains unchanged.
- Demo/sample data should be loaded from a small curated slice of `evals/golden_set/cases.jsonl`, ideally two or three representative cases:
  - one clean domestic match
  - one import case
  - one unreadable or needs-review case
- The app should expose:
  - `GET /` for the reviewer landing page
  - `GET /healthz` for smoke and deployment checks
  - `POST /verify` for live verification
  - a simple sample-loading mechanism, either embedded on `/` or via a dedicated helper route

## Work Plan

## Task 1: Finish the minimal reviewer web surface
**Files**
- Create: `app/main.py`
- Create: `app/templates/index.html`
- Create: `app/templates/result.html`
- Create: `tests/test_web.py`

**Implementation**
- Build the minimum single-label reviewer flow from PRD 02 if it is still absent:
  - upload one image
  - enter or prefill the seven tracked application fields
  - submit to the real verifier
  - render overall verdict, recommended action, and field-by-field results
- Add a lightweight `GET /healthz` endpoint for smoke checks and Railway validation.
- Keep the UI narrow and demo-oriented; do not add batch controls, auth, persistence, or OCR-debug-heavy panels.

**Acceptance**
- `GET /` returns `200`.
- `GET /healthz` returns `200` with a simple readiness payload.
- `POST /verify` can process one real label image end to end and render a terminal result.
- Web tests cover the landing page, health endpoint, and at least one verification flow.

## Task 2: Add a guided sample/demo path
**Files**
- Create: `app/demo_cases.py` or `app/demo_cases.json`
- Modify: `app/main.py`
- Modify: `app/templates/index.html`
- Modify: `README.md`

**Implementation**
- Curate a tiny subset of golden-set cases for reviewer demos rather than exposing all 28 cases.
- Surface at least one "clean match" sample and one "needs review" sample.
- Provide matching expected values in one of two acceptable ways:
  - a sample selector that prefills the form in the UI
  - a README table that lists the exact sample image and its expected payload
- Keep fixture paths repo-local and stable so the smoke test can reuse them.

**Acceptance**
- A reviewer can reach a successful sample submission in under 2 minutes using only the repo docs and landing page guidance.
- The sample path is visible without digging through eval internals.

## Task 3: Make the repo runnable in a reproducible way
**Files**
- Modify: `Dockerfile`
- Modify: `pyproject.toml` only if dependency groups need correction
- Optionally create: `railway.json`
- Create: `README.md`

**Implementation**
- Change the Docker image to install the web dependencies and launch `uvicorn app.main:app`.
- Keep OCR/runtime libraries inside the container build.
- Make Docker the primary "clean machine" path in the README because it is the most honest cross-platform setup for current OCR constraints.
- If a native path is documented, mark it clearly as Linux x86_64-oriented and secondary to Docker.
- Document the exact local commands for:
  - build
  - run
  - open app
  - run evals

**Acceptance**
- A reviewer can build and run the app locally using only the README quick start.
- The documented container path does not rely on undeclared manual setup.

## Task 4: Write the reviewer-facing docs
**Files**
- Create: `README.md`
- Create: `docs/approach.md`

**Implementation**
- `README.md` should include:
  - what the project is
  - scope limits: distilled spirits only, single-label first
  - Docker-first quick start
  - local run instructions
  - eval instructions
  - sample/demo path
  - deployed demo link section
  - known limitations and privacy posture
- `docs/approach.md` should stay short and decision-oriented:
  - local-first OCR plus deterministic validation
  - why scope is distilled-spirits-only
  - why `needs_review` is part of the design
  - what is intentionally not production-ready

**Acceptance**
- README plus approach note answer the likely reviewer questions without requiring a live walkthrough.
- All repo-local links in the docs resolve.

## Task 5: Create automated smoke validation
**Files**
- Create: `scripts/smoke_test.sh`
- Optionally create: `scripts/smoke_submit_sample.py`

**Implementation**
- `scripts/smoke_test.sh` should validate:
  - local app boot via background server process
  - `GET /healthz`
  - one seeded local sample submission returning a terminal verdict
  - `python3 evals/run_golden_set.py` against the real verifier
  - deployed availability through `SMOKE_BASE_URL` or similar env configuration
- Keep the script deterministic and CI-friendly:
  - fail fast on missing commands
  - clean up background processes
  - print a short pass/fail summary
- Do not try to encode the manual README dry run in the script.

**Acceptance**
- The script passes locally.
- The same script can be pointed at the deployed base URL for final release checks.

## Task 6: Deploy and run release gates
**Files**
- Modify deployment config files as needed
- No new product scope files beyond docs and smoke tooling

**Implementation**
- Deploy the container to Railway.
- Confirm public access without credentials.
- Run the release gates defined in PRD 04:
  - README dry run from a clean shell or fresh container context
  - deployed demo dry run in a fresh browser session
  - three consecutive smoke-test passes on the final candidate
- Freeze docs, sample data, and demo steps once the candidate is stable.

**Acceptance**
- The deployed URL supports the same seeded sample path described in the docs.
- Final handoff includes repo URL, deployed URL, README, approach note, and smoke-test evidence.

## Verification Commands
```bash
python3 evals/run_golden_set.py
python3 -m pytest tests/test_web.py -q
docker build -t alc-levels .
docker run --rm -p 8000:8000 alc-levels
SMOKE_BASE_URL=http://localhost:8000 bash scripts/smoke_test.sh
SMOKE_BASE_URL=https://<railway-app>.up.railway.app bash scripts/smoke_test.sh
```

## Recommended Execution Order
1. Finish the minimal web surface and tests.
2. Add the guided sample/demo path.
3. Switch the Dockerfile to app-serving mode.
4. Write README and approach docs against the real local run path.
5. Add and stabilize `scripts/smoke_test.sh`.
6. Deploy to Railway and run the final release gates.

## Cut Line
- Must ship:
  - single-label web app
  - guided sample path
  - Docker-first README
  - approach note
  - smoke test
  - deployed URL
- Nice to have only if everything above is already green:
  - `railway.json`
  - extra sample cases beyond the minimum guided set
  - video walkthrough

## Risks to Watch During Implementation
- The biggest risk is letting M4 silently become a broader UI build. Keep the web surface minimal and only complete what the reviewer demo needs.
- Docker may become the only honest reproducible path for OCR. That is acceptable as long as the README is explicit and the deployed demo works.
- The smoke test can become flaky if it depends on brittle HTML parsing. Prefer stable endpoints and deterministic sample inputs.
- Reusing golden-set fixtures is efficient, but the reviewer-facing docs should present them as curated demo samples rather than raw eval internals.
