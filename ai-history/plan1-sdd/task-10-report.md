# Task 10 report: Refresh job, seed snapshot, classification eval

**Status:** DONE_WITH_CONCERNS. Commit `4bf4aca feat: refresh job, seed snapshot, classification eval` (BASE 9088748).

## What I implemented
- **`backend/scripts/refresh.py`**: `refresh(conn, days=30, use_llm=True) -> dict` and the CLI `--days N [--no-llm] [--out PATH]`.
  - Filings: `ingest_filings` over the 18 portfolio symbols for the window [now−days, now] (IST).
  - Prices: `fetch_eod(holdings)` with its default `3mo` period, upserted with `upsert_prices`. `prices_as_of` (IST ISO now) is set only when bars came back.
  - Classification: `classify_pending`.
  - Error handling (Ruling 4): `NSEUnavailable` prints a message, keeps the existing filings (ingest is atomic, so `filings_as_of` does not advance) and carries on to prices. Any exception from yfinance prints and continues; this is a deliberate broad catch with `# noqa: BLE001`. An empty bar list also counts as an error. Neither case raises.
  - `use_llm=True` with the classify route's key empty (GROQ_API_KEY, looked up through `route_for` and `PROVIDERS`) prints a note and falls back to rules only.
  - Summary keys: `filings_new, price_bars, price_symbols, classify{rules,llm,default}, filings_total, unclassified_left, errors[]`, plus `llm` (from `router.stats()`) when the LLM was used.
  - The CLI runs `PRAGMA wal_checkpoint(TRUNCATE)` and closes the connection, prints the summary as JSON, and exits 1 if `errors` is non-empty, otherwise 0.
- **`backend/scripts/eval_classify.py`**: `--no-llm` runs rules only and gives rule misses the pipeline default. The default mode sends rule misses to `classify_batch_llm` and reuses the llm_cache in DB_PATH. LLM mode with no key exits 2 with a hint.
  - Metrics follow Ruling 3 exactly: overall accuracy (a noise row matches when the prediction has noise=True), material accuracy (gold base ≥ 45), rules coverage, and a list of misses (seq_id, gold → predicted, subject[:80]).
  - Output is Markdown, ready to paste into EVALS.md.
- **`backend/tests/fixtures/gold/classification.jsonl`**: 104 rows; details below.
- **`backend/finn/api/main.py`**: a lifespan handler calls `copy_seed_if_missing(settings.db_path, SEED_PATH)`. `SEED_PATH` is `backend/seed/finn.sqlite`, resolved relative to the package rather than the working directory. The handler uses `shutil.copyfile`, creates the parent directory, and never overwrites an existing DB.
- **`backend/seed/finn.sqlite`** (344 KB): built live and committed with `git add -f`. No `-wal` or `-shm` files exist or were committed.
- **`docs/EVALS.md`**: describes the gold set (seed, method and a reproducing snippet), states that the labels were written by Claude and are pending the author's 20-row spot-check, defines the metrics, and gives the rules-only results, the LLM row marked pending with its run command, the miss list, and an analysis of what the LLM can fix.
- **`backend/pyproject.toml`**: adds `pythonpath = ["."]` to the pytest options so tests can `import scripts.refresh` and `scripts.eval_classify`.

## Gold set (blind, Ruling 2)
- **Sampling:** `random.Random(20261108)`. Descs are taken in sorted order. Within each desc, rows are sorted by seq_id and ceil(25%) are drawn, minimum 1. I wrote the sampler in my scratchpad and published the equivalent snippet in EVALS.md; I checked that it reproduces the gold seq_ids exactly, in order.
- **Coverage:** 104 rows covering all 45 descs, 48 of them from ambiguous descs (the brief requires ≥ 80 rows and ≥ 25 ambiguous).
- **How I labelled:** I printed only seq_id, symbol, desc, subject and summary for the sampled rows. I labelled every row against PROJECT_BRIEF §5 and finished the file before running any classifier on these rows. sha256 `b3b0a26a…802d549` was recorded before the first eval run, and `sha256sum -c` confirmed it unchanged afterwards. No label was changed after I saw any output.
- **Notes:** 36 rows carry `notes` for judgment calls. The main ones:
  - Newspaper ads of results are labelled noise, per your noise list, with a note that ENAM's taxonomy lists them under results.
  - Subsidiary IPOs (Jio Platforms ×2, IL JIN) are labelled mna, not fund_raise.
  - "Agreements" and share-swap buyouts are labelled mna.
  - Liquidation or strike-off of a subsidiary is labelled unclassified.
  - Investor presentations filed in results season are labelled results/presentation.
  - A news-verification filing about a regulator-ordered production halt is labelled press_release.
- **Caveat:** I read the rules source before labelling, since I had to understand the codebase. I labelled from the taxonomy, not by mentally running the rules, and several labels contradict the rules (see the misses below).

## Eval results
Rules only (`uv run python scripts/eval_classify.py --no-llm`):

| metric | value |
|---|---|
| overall accuracy | 85.6% (89/104) |
| material-category accuracy (gold base ≥ 45) | 84.8% (39/46) |
| rules coverage | 80.8% (84/104) |

There are 15 misses; EVALS.md lists them all. The LLM-assisted row is marked pending API keys (Ruling R3/R11).

## Live refresh (Step 2), 2026-11-08 22:29 IST
Command: `uv run python scripts/refresh.py --days 30 --no-llm --out seed/finn.sqlite` (exit 0, 4.6 s)
```
{
  "filings_new": 317,
  "price_bars": 1170,
  "price_symbols": 18,
  "classify": {"rules": 253, "llm": 0, "default": 64},
  "filings_total": 317,
  "unclassified_left": 0,
  "errors": []
}
```
Checked in the seed afterwards, opened read-only and immutable:
- 18 distinct symbols in filings and 18 in prices (65 bars each).
- Prices run from 2026-08-06 to 2026-11-08; filings from 2026-10-09 to 2026-11-07.
- `filings_as_of` and `prices_as_of` are both set.
- 27 filings are marked noise, and `llm_calls` is empty.

## TDD evidence
- **RED:** `uv run pytest -q tests/test_refresh.py tests/test_eval_classify.py tests/test_api.py`
  - test_refresh failed with `ImportError: cannot import name 'refresh' from 'scripts'`, and test_eval_classify with `cannot import name 'eval_classify'`. Both modules did not exist yet, as expected.
  - `uv run pytest -q tests/test_api.py` gave `5 failed, 11 passed`. The new seed tests failed with an ImportError for `copy_seed_if_missing` and an AttributeError for `SEED_PATH`.
- **GREEN:** `tests/test_api.py` passed 16; `tests/test_refresh.py` passed 7; `tests/test_eval_classify.py` passed 9, then 10 after I added the LLM-mode CLI test.
- **Final:** `uv run pytest -q` passed 152 in 2.14 s with no warnings, and `uv run ruff check .` reported "All checks passed!".
- **Order lapse:** I wrote the gold data file before its integrity test, so that test passed on its first run.

## Tests added
- **test_refresh (7):**
  - Happy path: 323 filings and 18 symbols of prices, 0 unclassified, both `as_of` keys set.
  - NSE 403: existing filings kept, `filings_as_of` not advanced, prices still fetched, message printed.
  - A yfinance exception, and separately an empty bar list: reported, `prices_as_of` not set.
  - `use_llm` with no keys degrades to rules and prints the note.
  - With a key, rule misses go to a respx-mocked Groq.
  - The CLI `--out` writes a standalone file with no WAL file left behind.
- **test_api (+5):** the seed is copied (creating nested directories), an existing DB is never overwritten, no seed means no copy, and the lifespan copies to `settings.db_path` (via `with TestClient`). `SEED_PATH` points at `backend/seed/finn.sqlite`.
- **test_eval_classify (10):**
  - Gold integrity: row shape, valid categories, rows match the fixture, every desc covered, ≥ 25 ambiguous.
  - Match semantics and `evaluate` counts, including noise labels in the miss list.
  - `predict`: rules only defaults the misses; only rule misses reach the LLM.
  - CLI: `--no-llm` prints the table; LLM mode with no key exits 2; LLM mode with mocked Groq works.
- External calls are mocked only at the edges: NSE and Groq over HTTP with respx, and `fetch_eod` monkeypatched, because yfinance is not HTTP-mockable in any simple way.

## Self-review
- **Fixed:** in-function imports moved to module level in test_api; ruff ISC004 and RUF059; restructured `eval_classify.main` so `provider` and `model` are never conditionally bound.
- Every brief requirement and Rulings 1–7 are covered.
- `predict()` in the eval mirrors `classify_pending` but does not persist to the DB, so the eval stays side-effect free apart from the LLM cache.

## Choices the brief left open
1. Prices are always fetched for `3mo`, whatever `--days` is: the alert engine needs a 20-session baseline and the API reads 60 bars. `--days` only sets the filings window.
2. The CLI exits 1 when `errors` is non-empty, so a cron job can tell a partial refresh happened. It still prints the summary and never shows a traceback.
3. The summary adds `price_symbols`, `filings_total`, `unclassified_left` and, in LLM runs, `llm` (router stats, cumulative over `llm_calls`), so the Step 2 expectations can be checked.
4. The eval prints Markdown and does not rewrite EVALS.md itself; the numbers were pasted in by hand.
5. Non-noise rows match on category alone, exactly as Ruling 3 says. I checked that no non-noise gold row is predicted as noise, so a stricter reading would give the same numbers.

## Concerns
1. **The ≥ 90% LLM target is at risk.**
   - Of the 7 material misses, only 3 are rule misses the LLM will see: 106852258 (litigation), 106832075 (results) and 106821846 (results).
   - The other 4 are confident rule hits the LLM never sees: two subsidiary IPOs labelled fund_raise via the `initial public offer` rule, the Jio listing labelled results via the intimation rule, and an "Agreements" share swap labelled press_release via DESC_MAP.
   - So LLM-assisted material accuracy is at most 42/46 = 91.3%, and one LLM error drops it to 89.1%.
   - I did not tune the rules. That would change Task 4's code before the LLM number exists, and two of the four involve judgment-call labels (subsidiary IPO as mna).
   - Candidate fixes if the LLM run lands below 90%: treat a subsidiary's IPO, DRHP or RHP as mna; check the mna keywords before DESC_MAP's partnership mapping for the "Agreements" desc.
2. **The LLM classifier cannot emit noise** (its prompt has no noise flag), so a noise row the rules miss stays a miss in either mode (106819825).
3. **Resolved in fix round 1:** rows that took the default are now retried. Re-running `uv run python scripts/refresh.py --days 30 --out seed/finn.sqlite` with keys set upgrades the 64 seed rows that got the default; the seed does not have to be deleted first. The same applies to a production DB refreshed while keys were missing.
4. The seed file's header records WAL mode (bytes 18–19 = 2), which is harmless since `db.connect` sets WAL anyway. The month has no insider_trading or pledging filings, so the gold set has none.
5. I labelled 106844222 ("allotment … pursuant to Non Convertible Securities", Persistent) as fund_raise, taking the subject at face value. It reads oddly for Persistent and is a candidate for the spot-check.

## Files changed
- backend/scripts/refresh.py (new)
- backend/scripts/eval_classify.py (new)
- backend/tests/fixtures/gold/classification.jsonl (new)
- backend/seed/finn.sqlite (new, binary)
- backend/tests/test_refresh.py (new)
- backend/tests/test_eval_classify.py (new)
- backend/tests/test_api.py (seed-copy tests)
- backend/finn/api/main.py (lifespan seed copy)
- backend/pyproject.toml (pytest pythonpath)
- docs/EVALS.md (new)

---

## Fix round 1 (Ruling R12): retry filings that took the default when an LLM is available

**Gap:** `classify_pending` only picked up `category IS NULL`. Rows that got the default (by='default') during a keyless run, such as the 64 in the seed, were never retried by a later keyed refresh.

### Changes
- `backend/finn/db.py`: new `default_classified_filings(conn) -> list[Filing]`, which returns rows with `classified_by = 'default'` ordered by `filed_at, seq_id`.
- `backend/finn/classify/pipeline.py`: when `router is not None`, `classify_pending` starts its LLM list with `db.default_classified_filings(conn)` and adds the new rule misses to it. The rules are not re-run on those rows, because they already missed. Results are persisted through `save_classifications` as before.
  - With `router is None`, rows that took the default are neither queried nor touched.
  - The counts dict keeps its shape: an upgraded row counts under "llm", and a row the LLM fails on again counts under "default".
- `docs/EVALS.md` and the report's concern 3 now say that re-running `scripts/refresh.py` with keys is enough; they no longer tell you to `rm` the seed.
- `backend/seed/finn.sqlite` was not rebuilt or modified.

### Covering tests
- `tests/test_classify_llm.py::test_pending_retries_default_rows_when_router_available`: a row that took the default during a keyless run, plus a new rule miss, both go to a FakeRouter. Counts are `{"rules":0,"llm":2,"default":0}`, the row is stored as capex/by=llm, and none are left at the default.
- `tests/test_classify_llm.py::test_pending_retry_that_fails_stays_default`: the router raises LLMError. Counts are `{"rules":0,"llm":0,"default":1}` and the row stays at the default.
- `tests/test_classify_llm.py::test_pending_without_router_leaves_default_rows_alone`: with router None, a row that already took the default is not re-counted, so only the new row counts (`default: 1`), and both stay at the default.
- `tests/test_refresh.py::test_keyed_refresh_upgrades_rows_defaulted_by_a_keyless_run`: end to end, a `--no-llm`-style refresh is followed by a keyed refresh with Groq mocked by respx. The second run has `filings_new == 0`, `llm` equals the first run's `default` count (66 on the fixture), and no row is left at the default.
  - Against the pre-fix `pipeline.py` (git stash), this test fails with `{'llm': 0} != {'llm': 66}`.
- Refactor: the Groq mock and the keyed-settings setup in test_refresh moved into the shared helpers `_groq` and `_keyed`.

### TDD
- RED: `uv run pytest -q tests/test_classify_llm.py` gave `3 failed, 10 passed`. The failures were `AttributeError: module 'finn.db' has no attribute 'default_classified_filings'`, `{'llm': 1} != {'llm': 2}` and `{'default': 0} != {'default': 1}`.
- GREEN: `uv run pytest -q tests/test_classify_llm.py tests/test_refresh.py` passed 21 in 0.95 s.
- Full suite: `uv run pytest -q` passed 156 in 2.08 s with no warnings. `uv run ruff check .` reported "All checks passed!".

### Note
On every keyed refresh, any row still at the default is retried; only LLM failures stay at the default. A row whose LLM reply keeps failing validation is therefore resent each run. That costs little, since the batches are small and the cache absorbs identical batches, but it is unbounded.
