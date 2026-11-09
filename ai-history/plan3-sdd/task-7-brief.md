### Task 7: Dossier pipeline, storage, API with SSE, and CLI

**Files:**
- Create: `backend/finn/research/pipeline.py`, `backend/scripts/research.py`
- Modify: `backend/finn/db.py` (`dossiers` table), `backend/finn/models.py` (`Dossier`), `backend/finn/api/main.py`
- Test: `backend/tests/test_research_pipeline.py`, `backend/tests/test_api_research.py`

**Interfaces:**
```python
class Dossier(BaseModel):
    symbol: str
    name: str | None
    basis: str
    built_at: datetime
    sources: list[Source]   # API responses omit `pages` (see below)
    ledger: Ledger | None
    snapshot: Snapshot | None
    trajectory: Trajectory | None
    health: BalanceSheetHealth | None
    bull: list[Point]
    bear: list[Point]
    notes: list[str]        # every skipped/failed section with its reason
    cost: dict              # router.stats() delta: calls, cached, input_tokens, output_tokens, usd_list_price
    build_seconds: float

def build_dossier(conn, symbol: str, router, *, screener_client=None, doc_client=None,
                  progress: Callable[[str], None] = lambda m: None, deadline_s: float = 240) -> Dossier
```
- **Tables:** `dossiers(symbol TEXT PRIMARY KEY, built_at TEXT, payload_json TEXT)` with `save_dossier`, `get_dossier` and `list_dossiers`. Store the dossier **with** source pages, because citation excerpts are served from it.
- **API:**
  - `GET /research` → `[{symbol, name, built_at, counts}]`, read-only.
  - `GET /research/search?q=` → screener search (network allowed). Empty q gives 422.
  - `GET /research/{symbol}` → the cached dossier without source `pages`, or 404 `{"detail": "not built", "build": "/research/{SYM}/build"}`.
  - `GET /research/{symbol}/source/{source_id}/{page}` → `{title, page, text}` for citation chips, read-only, 404 if absent.
  - `GET /research/{symbol}/build` → `text/event-stream`. It emits `event: progress` with `data: {"msg": …}` for each progress message, then `event: done` with the dossier JSON (minus pages), or `event: error` with `{"detail": …}`. The built dossier is saved. A build that finishes within 10 minutes of a cached `built_at` is not re-run; the cached one streams immediately.
- **CLI:** `scripts/research.py SYM [SYM…] [--out DB]` builds and saves each dossier and prints a one-line summary per symbol (row counts, cost, seconds). It exits 0.
- **Progress messages, in order:** "Resolving {SYM} on screener", "Found {n} transcripts and {m} annual report(s)", "Reading {title}" (per source), "Extracting guidance from {title}", "Checking delivery on {k} promises", "Writing snapshot and bull/bear", "Done in {s:.0f}s".

- [ ] **Step 1: Write failing tests:**
  - `build_dossier` end to end, offline:
    - a fake screener client returns `PERSISTENT_screener.html`;
    - `doc_pages` is pre-seeded from the transcripts fixture, and a fake DocClient makes the AR fail;
    - a FakeRouter with a callable reply per task returns real quotes from the fixture;
    - the dossier has 4 sources, a ledger with rows, a trajectory, health and notes mentioning the annual report;
    - the progress messages come in order;
    - the cost dict is present.
  - A deadline of 0 s skips the LLM sections with a note, and the dossier still has its trajectory and health.
  - An unknown symbol (the screener client raises `ScreenerError`) raises `ScreenerError` from `build_dossier`. This is the one error that does propagate, so the API can say "not found".
  - API (TestClient):
    - list;
    - get 404 with the build link;
    - get 200 after save, without `pages`;
    - source page 200 and 404;
    - SSE build with monkeypatched `build_dossier` and progress gives `progress` events then `done`;
    - SSE build for an unknown symbol gives an `error` event;
    - search with q empty gives 422.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.** SSE uses `StreamingResponse` over a generator. Run `build_dossier` in a thread with a `queue.Queue` for progress messages, and yield them as they arrive.
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): dossier pipeline, cache, SSE build endpoint and CLI`.

---

