# Simulate COLA Submission — Demo Affordance

**Date:** 2026-04-19
**Status:** Draft — awaiting approval

## Context

The review queue is seeded with 3 fixed demo items. Reviewers currently have
no way to add more, which makes it hard to demo the flow at any scale beyond
"open, verify, approve" three times. This plan adds a one-click "Simulate
submission" button that picks a golden-set case not already in the queue,
fabricates realistic metadata (COLA ID, submitter, timestamp), and appends it
as a new `pending` item.

This is explicitly a **demo affordance**. In real production, applications
arrive from COLA upstream — reviewers do not create them. The button is
labeled clearly so evaluators understand the intent.

## Design decisions

1. **Pool = all 28 golden-set cases.** Reading from `evals/golden_set/cases.jsonl`
   gives us application payloads, image paths, and a mix of verdicts
   (match, mismatch, needs_review, import, domestic) for free.
   Alternative considered: curated subset of ~10. Rejected — variety > brevity
   for a demo.

2. **Queue ID = case_id.** New items use the golden-set `case_id` (e.g.,
   `gs_014`) as their queue `id`. This gives us natural uniqueness —
   adding the same pool entry twice is impossible by construction, which
   is what drives the "button disabled when exhausted" UX.

3. **Submitter derivation rules (mechanical, no hand-mapping):**
   - Domestic: `titlecase(brand_name) + " LLC"`
   - Import:   `titlecase(brand_name) + " Imports"`
   Good enough for demo; seeded items retain their hand-crafted submitters.

4. **COLA ID format:** `COLA-{YYYY}-{MMDD}-{NNN}` where `NNN` is random 001–999.
   Regenerate on collision (extremely rare in practice).

5. **Persistence: opt-in, env-var-driven.** `QUEUE_PERSIST_PATH` env var points
   at a JSON file.
   - Unset (default) → in-memory only, same behavior as today
   - Set → read on startup, rewrite atomically on every queue mutation
   For cross-redeploy persistence on Railway the user must additionally
   mount a volume at that path — documented but not required.

6. **Exhaustion UX:** When all 28 cases are already in the queue, render the
   simulate button as `disabled` with a `title` tooltip explaining why. The
   POST endpoint also returns 409 on exhaustion as a defence-in-depth
   against concurrent clicks.

## Phase 1 — queue_state: add_item + persistence

### Task 1.1 — add_item helper (TDD)

**Tests** in `tests/test_queue_state.py`:

```python
class TestAddItem:
    def test_add_item_appends_and_returns(self):
        reset_queue()
        item = add_item(
            id="gs_007",
            application_id="COLA-2026-0419-042",
            submitter="Acme Distillery LLC",
            submitted_at=datetime(2026, 4, 19, 14, 30),
            beverage_class="Distilled Spirits",
            origin_badge="Domestic",
            image_path=Path("evals/golden_set/fixtures/gs_007.png"),
            form_values={"brand_name": "ACME", ...},
        )
        assert item.id == "gs_007"
        assert item.status == QueueStatus.PENDING
        assert get_item("gs_007") is item
        assert len(list_items()) == 1

    def test_add_item_duplicate_id_raises(self):
        reset_queue()
        seed_queue()  # gs_001 already present
        with pytest.raises(ValueError, match="already in queue"):
            add_item(id="gs_001", ...)
```

**Implementation** in `app/queue_state.py`: new function `add_item(**kwargs)` —
validates `id` not already in `_QUEUE`, constructs `QueueItem`, inserts.

### Task 1.2 — JSON persistence (TDD)

**Tests** in `tests/test_queue_state.py`:

```python
class TestPersistence:
    def test_save_writes_all_items(self, tmp_path):
        path = tmp_path / "queue.json"
        reset_queue()
        seed_queue()
        save_to_disk(path)
        data = json.loads(path.read_text())
        assert len(data["items"]) == 3
        ids = {it["id"] for it in data["items"]}
        assert ids == {"gs_001", "gs_003", "gs_020"}

    def test_roundtrip_preserves_status_and_verdict(self, tmp_path):
        path = tmp_path / "queue.json"
        reset_queue()
        seed_queue()
        mark_in_review("gs_001", {"overall_verdict": "match", ...})
        save_to_disk(path)

        reset_queue()
        load_from_disk(path)
        item = get_item("gs_001")
        assert item.status == QueueStatus.IN_REVIEW
        assert item.verdict["overall_verdict"] == "match"

    def test_load_missing_file_is_noop(self, tmp_path):
        reset_queue()
        load_from_disk(tmp_path / "nope.json")
        assert list_items() == []

    def test_save_writes_atomically(self, tmp_path):
        # Save twice; verify final file parses and has latest state
        path = tmp_path / "queue.json"
        reset_queue()
        seed_queue()
        save_to_disk(path)
        mark_in_review("gs_001", {"overall_verdict": "match"})
        save_to_disk(path)
        data = json.loads(path.read_text())
        g001 = next(it for it in data["items"] if it["id"] == "gs_001")
        assert g001["status"] == "in_review"
```

**Implementation**:
- `save_to_disk(path: Path)` — serialises `_QUEUE` values. `Path` → str,
  `datetime` → ISO string, enums → `.value`. Writes to `path.with_suffix(".json.tmp")`,
  then `os.replace()` for atomicity.
- `load_from_disk(path: Path)` — if missing, returns silently. Otherwise
  parses JSON, reconstructs `QueueItem`s, replaces `_QUEUE` contents.

### Task 1.3 — autosave wiring

**Change**: add a module-level `_PERSIST_PATH: Optional[Path] = None` and
`configure_persistence(path: Path | None)` setter. When set, `add_item`,
`mark_in_review`, `mark_complete` call `save_to_disk(_PERSIST_PATH)` at the
end. Test with a tmp path that `add_item` then exits and a fresh load sees
the item.

### Task 1.4 — app lifespan hookup

**Change** in `app/main.py` lifespan:

```python
persist_path = os.getenv("QUEUE_PERSIST_PATH")
if persist_path:
    p = Path(persist_path)
    configure_persistence(p)
    load_from_disk(p)
    if not list_items():
        seed_queue()
        save_to_disk(p)
else:
    seed_queue()
```

**Test**: spin up app with `QUEUE_PERSIST_PATH` set to a tmp path, verify
first boot seeds + writes, second boot (fresh process) reads back the same
items.

## Phase 2 — simulation pool + endpoint

### Task 2.1 — pool module (TDD)

**Tests** in `tests/test_simulation_pool.py`:

```python
def test_pool_has_28_entries():
    assert len(POOL_CASES) == 28

def test_pool_entries_have_image_paths_that_exist():
    for case in POOL_CASES.values():
        assert case.image_path.exists()

def test_pick_unqueued_excludes_given_ids():
    case = pick_unqueued_case({"gs_001", "gs_002"})
    assert case.case_id not in {"gs_001", "gs_002"}

def test_pick_unqueued_returns_none_when_exhausted():
    all_ids = set(POOL_CASES.keys())
    assert pick_unqueued_case(all_ids) is None

def test_generated_submitter_for_domestic():
    case = POOL_CASES["gs_001"]  # domestic bourbon
    assert derive_submitter(case) == "Old Tom Distillery LLC"

def test_generated_submitter_for_import():
    case = POOL_CASES["gs_003"]  # import tequila
    assert derive_submitter(case).endswith(" Imports")
```

**Implementation** in `app/simulation_pool.py`:
- Load `evals/golden_set/cases.jsonl` at module import, build
  `POOL_CASES: dict[str, PoolCase]` keyed by `case_id`.
- `PoolCase` dataclass mirrors the relevant subset (case_id, image_path,
  form_values, is_import, brand_name).
- `pick_unqueued_case(queued_ids)` — filters then `random.choice`.
- `derive_submitter(case)` — rule above.

### Task 2.2 — POST /queue/simulate (TDD)

**Tests** in `tests/test_queue_web.py`:

```python
class TestQueueSimulate:
    def test_simulate_adds_item_and_redirects(self, client):
        r = client.post("/queue/simulate", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        # 3 seeded + 1 new
        assert len(list_items()) == 4

    def test_simulate_new_item_visible_on_landing(self, client):
        client.post("/queue/simulate")
        r = client.get("/")
        # At least one COLA id that is NOT one of the three seeded ones
        seeded = {"COLA-2026-0412-001", "COLA-2026-0413-027", "COLA-2026-0415-009"}
        import re
        found = set(re.findall(r"COLA-\d{4}-\d{4}-\d{3}", r.text))
        assert found - seeded  # non-empty difference

    def test_simulate_when_exhausted_returns_409(self, client):
        # Seed 28 manually by repeatedly calling add_item for every pool entry
        reset_queue()
        for case_id, case in POOL_CASES.items():
            add_item(id=case_id, ...)
        r = client.post("/queue/simulate")
        assert r.status_code == 409

    def test_simulate_picks_case_not_already_queued(self, client):
        # Seed all but one; simulate should pick the missing one
        reset_queue()
        missing = "gs_014"
        for case_id in POOL_CASES:
            if case_id == missing:
                continue
            add_item(id=case_id, ...)
        client.post("/queue/simulate")
        assert get_item(missing) is not None
```

**Implementation** in `app/main.py`:

```python
@app.post("/queue/simulate")
async def simulate_submission():
    queued_ids = {item.id for item in list_items()}
    case = pick_unqueued_case(queued_ids)
    if case is None:
        return JSONResponse(
            status_code=409,
            content={"error": "All pool cases are already in the queue."},
        )
    now = datetime.now()
    origin = "Import" if case.is_import else "Domestic"
    add_item(
        id=case.case_id,
        application_id=_generate_cola_id(now, queued_ids),
        submitter=derive_submitter(case),
        submitted_at=now,
        beverage_class="Distilled Spirits",
        origin_badge=origin,
        image_path=case.image_path,
        form_values=case.form_values,
    )
    return RedirectResponse(url="/", status_code=303)
```

`_generate_cola_id` retries on collision with existing `application_id`s.

## Phase 3 — UI

### Task 3.1 — Simulate button on queue landing (TDD)

**Tests**:

```python
def test_landing_shows_simulate_button(self, client):
    r = client.get("/")
    assert 'action="/queue/simulate"' in r.text
    assert "Simulate submission" in r.text

def test_landing_simulate_button_disabled_when_pool_exhausted(self, client):
    reset_queue()
    for case_id in POOL_CASES:
        add_item(id=case_id, ...)
    r = client.get("/")
    assert "disabled" in r.text
    assert "All demo cases" in r.text  # tooltip text
```

**Implementation**:
- Pass `pool_exhausted: bool` into `queue.html` from the landing handler.
- Template renders:
  ```html
  <form method="post" action="/queue/simulate" class="queue-toolbar">
    <button type="submit"
            class="btn-primary"
            {% if pool_exhausted %}disabled title="All demo cases are already in the queue."{% endif %}>
      + Simulate submission
    </button>
  </form>
  ```
- CSS: `.queue-toolbar { display: flex; justify-content: flex-end; margin-bottom: 1rem; }`

### Task 3.2 — Empty-state message

When `items` is empty, show a friendly panel instead of an empty table.
Low priority; can skip if tight.

## Phase 4 — docs

### Task 4.1 — README

Update the "Guided demo path" section in `README.md`:

> The landing page is seeded with three pre-paired items. To demo with more
> variety, click **Simulate submission** — this pushes a random unqueued
> golden-set case (28 total) onto the queue with a fabricated COLA ID and
> submitter. The simulate button disables itself once all 28 are queued.
>
> By default the queue is in-memory and resets on process restart. To persist
> across restarts, set `QUEUE_PERSIST_PATH` to a writable JSON file path
> (on Railway, pair this with a mounted volume).

### Task 4.2 — approach.md

Add a short subsection to "Why queue-first":

> The queue is seeded with three hand-crafted items that showcase the three
> main verdicts. A **Simulate submission** button allows filling the queue
> with additional synthetic cases from the 28-item golden set — this is an
> intentional demo affordance, not a production submission channel. In
> production, applications flow from COLA upstream; reviewers never create
> them.

## Out of scope

- Custom label uploads as simulated submissions (already covered by `/test`)
- Editing or deleting queued items after creation
- Admin-only gating / authn — the Railway demo is intentionally open
- Real COLA webhook ingestion
- Queue pagination — 28 items is well under what a single page can show

## Verification

After all tasks:
- `pytest tests/test_queue_state.py tests/test_simulation_pool.py tests/test_queue_web.py -q` all green
- Smoke test (`bash scripts/smoke_test.sh`) still passes
- Manual: visit local server, click Simulate 28 times, confirm button disables
- Manual: with `QUEUE_PERSIST_PATH=/tmp/queue.json`, simulate once, restart process, confirm the new item is still there
- Manual: delete `/tmp/queue.json`, restart → queue re-seeds with the original 3
