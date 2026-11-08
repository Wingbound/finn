# Final-review fix wave: report

FIX_BASE 319671c → HEAD a5cd4a0, branch feat/push-backend. 10 commits, one per item group.
The final suite is **195 passed in 3.00s** (the baseline was 156) with no warnings, and
`uv run ruff check .` reports "All checks passed!". backend/seed/finn.sqlite and backend/.env
were not touched.

| commit | items |
|---|---|
| 985f34d fix(prices): exclude weekend special sessions | I1 |
| 5854227 fix(api): seed an empty store, keep script LLM caches out of it | I2 |
| 9b6ec73 fix(ingest): per-symbol filing ingest that never raises | I3 |
| 813303f fix(alerts): one time anchor for both alert kinds | I4 |
| e132f80 fix(classify): LLM subtypes follow the scoring contract | I5 |
| ab2529a docs(evals): state the in-sample caveat and rule precision | I6 |
| 22b8afe fix(classify): rules re-run on defaults, pledging rule, one default helper | M1, M3, M9 |
| 47df265 fix(llm): clamp retry-after, treat a corrupt cache row as a miss | M2 |
| 926cc66 fix(api): link alerts to filings, size history to the lookback | M4, M5, M8 |
| a5cd4a0 build: declare pandas, smoke-test the committed seed | M6, M7 |

Each item followed the same cycle: tests written first, run to see them fail (RED), code
changed, then the focused tests and the full suite run (GREEN).

---

## I1. Weekend special sessions (Muhurat)

**Changed**
- `finn/config.py` adds `FULL_SPECIAL_SESSIONS: frozenset[date] = frozenset()`. A comment
  explains that it holds weekend dates on which NSE ran a full session (for example a Saturday
  budget day), and that a date goes in only after NSE announces one.
- `finn/ingest/prices.py` `completed_sessions(bars, now, full_special_sessions=FULL_SPECIAL_SESSIONS)`
  drops the in-progress bar for today and every weekend-dated bar whose date is not on the
  allowlist. The volume-ratio heuristic is gone, along with its constants and the
  `statistics` import. Input order is kept; the only caller passes one symbol's bars in
  ascending order.
- `finn/api/main.py` `/portfolio` gives each holding a `date`: the ISO date of its last
  completed bar, or null when it has no bars.

**Tests** (`tests/test_prices.py`, `tests/test_api.py`)
- `test_muhurat_bar_with_normal_volume_excluded` is the VOLTAS regression: 25 weekday bars at
  620,300 shares plus a Sunday 2026-11-08 bar at 648,834. The Sunday bar must be dropped.
- `test_allowlisted_weekend_full_session_kept`: an allowlisted Saturday is kept, while the
  Sunday is still dropped.
- `test_full_special_sessions_empty_by_default`.
- The existing Muhurat test still passes. `test_normal_weekend_volume_kept` was replaced,
  because the behaviour it pinned is now the bug.
- The portfolio tests check `date == "2026-11-06"`, the new key set, and `date is None` when a
  holding has no bars.

**RED:** `uv run pytest -q tests/test_prices.py tests/test_api.py`
```
E       TypeError: completed_sessions() got an unexpected keyword argument 'full_special_sessions'
E       KeyError: 'date'
FAILED tests/test_prices.py::test_muhurat_bar_with_normal_volume_excluded - a...
FAILED tests/test_prices.py::test_allowlisted_weekend_full_session_kept - Typ...
FAILED tests/test_api.py::test_portfolio_has_18_rows_with_spark - KeyError: '...
```
The first run failed at collection with an ImportError, which was expected: the config
constant did not exist yet.

**GREEN:** `22 passed in 1.24s`. Full suite: `158 passed`.

## I2. Seed copy defeated by an empty DB

**Changed**
- `finn/config.py`
  - Adds `seed_path: Path`. It defaults to `Path(finn/config.py).resolve().parents[1] / "seed" / "finn.sqlite"`
    (that is, backend/seed/finn.sqlite) and can be overridden with env `SEED_PATH`.
  - Adds a property `llm_cache_path = data_dir / "llm_cache.sqlite"`.
- `finn/api/main.py`
  - `copy_seed_if_missing` is renamed `copy_seed_if_empty(db_path, seed_path)`. It copies the
    seed when the DB is missing or has no `filings` rows; a missing `filings` table also counts
    as empty.
  - It logs a warning when the seed file is absent.
  - It never overwrites a store that has filings, nor a file that is not a readable SQLite
    database. That second case logs a warning too.
  - Before copying, it deletes stale `-wal` and `-shm` sidecars so that an old WAL cannot be
    replayed onto the copied seed.
  - `lifespan` reads `settings.seed_path`. The module-level `SEED_PATH` constant is removed.
- `scripts/llm_smoke.py` and `scripts/eval_classify.py` now connect to
  `settings.llm_cache_path` instead of the serving DB.

**Tests** (`tests/test_api.py`, `tests/test_eval_classify.py`)
- `test_seed_copied_over_empty_initialised_db` covers the empty-DB case. It also checks that
  no `-wal` file is left behind.
- `test_seed_never_overwrites_populated_db` checks that a populated DB is untouched.
- `test_missing_seed_logs_warning` uses caplog on `finn.api.main`.
- `test_seed_never_overwrites_unreadable_db` keeps the old guarantee for a file that is not a
  database.
- `test_startup_copies_seed_to_settings_db_path` now sets the seed through `Settings(seed_path=...)`.
- `test_seed_path_defaults_to_committed_seed_and_reads_env` checks the default path and the
  `SEED_PATH` override.
- `test_cli_llm_mode_classifies_rule_misses` asserts that the serving DB is never created and
  that `llm_cache.sqlite` is.

**RED:** `uv run pytest -q tests/test_eval_classify.py`
```
E       AssertionError: assert not True
E        +  where True = exists()   # .../finn.sqlite: the eval created the serving DB
1 failed, 9 passed
```
`tests/test_api.py` failed at collection with
`ImportError: cannot import name 'copy_seed_if_empty'`.

**GREEN:** `28 passed in 1.28s`. Full suite: `160 passed`.

## I3. Refresh robustness, reversing R6 (ledger R14)

**Changed**
- `finn/ingest/nse.py`
  - `ingest_filings` returns `IngestResult(added, skipped, failed: dict[symbol, reason])` and
    never raises for NSE or row problems.
  - Each symbol is fetched and written on its own; `INSERT OR IGNORE` protects stored rows.
  - A malformed row (missing or invalid `an_dt`, missing keys, a non-dict) is skipped, counted
    in `skipped` and logged. The function catches KeyError, TypeError and ValueError, which
    includes pydantic's ValidationError.
  - A symbol that hits `NSEUnavailable` is recorded in `failed`, and the loop moves on.
  - `filings_as_of` advances only when `failed` is empty.
  - `SYMBOL_PAUSE_S = 0.5` is slept between symbols through the existing patchable `_sleep`.
  - `NSEUnavailable` is still raised by `NSEClient.fetch_announcements`.
- `scripts/refresh.py`
  - The filings stage, including `NSEClient()` construction, is wrapped in a broad
    `except Exception`, so the price stage always runs.
  - Each failed symbol becomes an `errors` entry: `filings: NSE announcements for X failed: …`.
  - `prices_as_of` is set to the timestamp taken right after `fetch_eod` returns.
  - The summary adds `filings_skipped` and `prices_missing`, the portfolio symbols that got no
    bars. When some bars did arrive, `prices: no bars for A, B` is also added to `errors`.

**Tests** (`tests/test_nse.py`, `tests/test_refresh.py`)
- `test_malformed_rows_are_skipped_and_counted` mixes the real RELIANCE rows with five bad
  ones: a missing `an_dt`, `an_dt="yesterday"`, an integer `an_dt`, a row with only `seq_id`,
  and a string.
- `test_failing_symbol_keeps_the_others_and_holds_as_of`: TRENT returns 403 on every attempt.
  RELIANCE's rows are still stored, `filings_as_of` stays unset, and the call count is 3 + 1.
- `test_persistent_403_is_recorded_not_raised` and `test_polite_pause_between_symbols`
  (sleeps `[0.5, 0.5]` for three symbols).
- `test_one_symbol_failing_keeps_the_rest_and_holds_filings_as_of` runs the same scenario
  through `refresh()`.
- `test_prices_still_run_when_the_filings_stage_crashes` patches `ingest_filings` to raise
  RuntimeError. It expects `errors == ["filings: RuntimeError: parser exploded"]`, 18 bars,
  and `prices_as_of` set.
- `test_prices_as_of_is_fetch_time_and_missing_symbols_listed`: AMBER and LODHA get no bars.
- The all-403 refresh test now expects 18 per-symbol errors.

**RED:** `uv run pytest -q tests/test_nse.py tests/test_refresh.py`
```
E       finn.ingest.nse.NSEUnavailable: NSE announcements for RELIANCE failed: HTTP 403
FAILED tests/test_nse.py::test_malformed_rows_are_skipped_and_counted - KeyEr...
FAILED tests/test_refresh.py::test_prices_still_run_when_the_filings_stage_crashes
... 10 failed, 11 passed
```

**GREEN:** `21 passed in 1.20s`. Full suite: `165 passed`.

## I4. One time anchor for alerts (ledger R15)

**Changed**
- `finn/db.py` adds `latest_filed_at(conn, symbols)`, which returns MAX(filed_at) or None.
- `finn/api/main.py`
  - `_alert_anchor` computes `min(now, max(latest filing filed_at, datetime.combine(last completed bar date, time.max, IST)))`.
    With no data at all, the anchor is `now`.
  - `/alerts` uses the window `[anchor − 7 d, anchor]`. Stories come from that window, and
    `evaluate_prices(..., start=start.date(), end=end.date())` limits price alerts to it.
  - The response adds `"window": {"start", "end"}`.
  - `ALERT_FILING_DAYS` is renamed `ALERT_WINDOW_DAYS`, and `ALERT_SESSIONS = 5` is added.
- `finn/alerts.py` `evaluate_prices` gains keyword arguments `start` and `end`. Bars after
  `end` are dropped before the last `sessions` bars are chosen. Of those, bars dated before
  `start` are skipped, but they still serve as the volume baseline and the previous close.
- `finn/digest.py` `build_digest` adds `latest_filing_at`: the newest portfolio filing
  regardless of window, or null.

**Tests**
- `test_alerts_on_stale_data_anchor_to_the_latest_data_point` sets now = the latest filing
  (7 Nov 16:58:42) + 12 days.
  - The window must be [31 Oct 16:58:42, 7 Nov 16:58:42].
  - Price, volume and filing alerts must all be present.
  - Every alert date must fall inside the window, so both kinds share it.
- `test_alerts_anchor_is_now_when_data_is_newer` covers the `min(now, …)` side: no price
  alerts come from a bar dated after `now`.
- `test_digest_latest_filing_at_null_without_filings`, and `latest_filing_at` asserted in the
  168h-window and empty-window digest tests.
- `test_price_window_limits_the_sessions_evaluated` is the unit test for `start` and `end`.

**RED:** `uv run pytest -q tests/test_api.py tests/test_alerts.py`
```
FAILED tests/test_api.py::test_digest_empty_window - KeyError: 'latest_filing...
FAILED tests/test_api.py::test_alerts_on_stale_data_anchor_to_the_latest_data_point
FAILED tests/test_api.py::test_alerts_anchor_is_now_when_data_is_newer - KeyE...
FAILED tests/test_alerts.py::test_price_window_limits_the_sessions_evaluated
6 failed, 24 passed
```

**GREEN:** `30 passed in 1.27s`. Full suite: `169 passed`.

## I5. LLM subtype contract

**Changed**
- `finn/classify/rules.py` makes `_management_subtype` and `_credit_subtype` public as
  `management_subtype` and `credit_subtype`, and gives them docstrings.
- `finn/classify/llm.py`
  - After the category is validated, `management_change` and `credit_rating` get the subtype
    derived by those helpers (`RULE_DERIVED_SUBTYPES`). The helpers read
    `nse_desc + subject + summary[:400]`, the same text the DESC_MAP path uses.
  - Every other category accepts the LLM subtype, after strip and lower-casing, only if it is
    in `LLM_SUBTYPES[category]`. That allowlist is built from the MODIFIERS keys for the
    category; anything else becomes None.
  - The system prompt lists the allowlist, generated from MODIFIERS with the reason labels:
    ```
    results: intimation (results intimation only), delay (results delay), presentation (investor presentation)
    earnings_call: transcript (call transcript), audio (call audio), notice (call notice)
    press_release: order_win (order win)
    fund_raise: allotment (allotment)
    litigation: auditor_resignation (auditor resignation)
    ```
  - `_parse_item` now looks the filing up in its batch. A reply id not in the batch is
    rejected there, which replaces the old `parsed[0] in out` check.

**Tests** (`tests/test_classify_llm.py`)
- `test_llm_credit_rating_subtype_comes_from_the_rules`: the filing is filed under General
  Updates and says CRISIL "reaffirmed", and the LLM replies with subtype
  "rating_reaffirmation". The result is subtype `reaffirm` and score 24, the same as the rule
  path for "Credit Rating- Others".
- `test_llm_management_change_subtype_comes_from_the_rules`: an independent-director
  appointment comes out as `independent`.
- `test_llm_subtype_kept_only_when_scoring_knows_it` checks kept, normalised, wrong-category,
  unknown and null subtypes.
- `test_llm_subtype_allowlist_is_the_modifier_table_and_is_in_the_prompt`.
- Two existing tests asserted free-form subtypes (`capex/new_plant`, `mna/stake_sale`). They
  now expect None.

**RED:** `ImportError: cannot import name 'LLM_SUBTYPES' from 'finn.classify.llm'`, raised at
collection because the new API did not exist yet.

**GREEN:** `51 passed in 0.11s` for test_classify_llm and test_rules. Full suite: `173 passed`.

## I6. EVALS honesty

**Changed**
- `docs/EVALS.md`
  - States that the eval is in-sample: the rules were tuned on portfolio_month.json and the
    gold set is sampled from the same file, so the numbers are not out-of-sample accuracy.
  - Defines the metrics *rules precision* and *default matches*.
  - Adds a rules-precision column (92.9%, 78/84).
  - Says that 11 of the 89 correct rows are default-`unclassified` matches. Without them, the
    rules alone got 78 of 104 right (75.0%).
- `scripts/eval_classify.py`
  - `evaluate()` adds `rules_correct`, `rules_precision` and `default_matches`, and `render()`
    prints both figures.
  - The docstring now reads "AI-labelled (Claude) gold set, pending author spot-check".

**Recomputed:** `uv run python scripts/eval_classify.py --no-llm`
```
| rules coverage | 80.8% (84/104) |
| rules precision (rows the rules labelled) | 92.9% (78/84) |
| correct rows that are default `unclassified` matches | 11 of 89 |
```

**Tests:** `test_rules_precision_and_default_matches` is a unit test of the counts and the
rendered rows. The rules-only CLI test asserts that both rows are printed.

**RED:** `KeyError: 'rules_correct'`, and the CLI output lacked "rules precision".

**GREEN:** `11 passed in 0.09s`.

## M1. Rules re-run on `by='default'` rows (R12 addition)

`finn/classify/pipeline.py` `classify_pending` now re-runs `classify_rules` on every
default-classified row first, whether or not a router is present. A rule hit is saved as
`by=rules` and counted. A row the rules still miss is retried on the LLM when there is a
router (as before), and otherwise left alone and not counted (also as before). The prior
LLM ordering is kept: default rows first, then new ones. The "Live snapshot" paragraph in
EVALS.md was updated to match.

**Tests:**
- `test_pending_reruns_rules_on_default_rows_without_router`: a "Dividend" row stored as
  default becomes `dividend` with `by=rules`.
- `test_pending_default_row_the_rules_now_catch_skips_the_llm`: the router is never called.

**RED:** both failed (`2 failed, 18 passed`). **GREEN:** passing within the full suite.

## M2. LLM router hardening

**Changed**
- `finn/llm/router.py`
  - `_retry_delay` returns the `retry-after` value clamped to [0, 60] s
    (`MAX_RETRY_AFTER_S`). A missing, non-numeric (HTTP-date), inf or nan value falls back to
    `BACKOFF_S[attempt]`.
  - `_cached()` treats a JSON decode error, or a cached value that is not an object, as a
    miss. The fresh reply then overwrites the row through the existing INSERT OR REPLACE.
- `finn/llm/costs.py` `list_price_usd` logs a warning for an unknown model, once per model
  (`functools.cache`), so cache hits and every batch don't repeat it.
- The comment on `classify/llm.py`'s ValueError catch was updated, since the router no longer
  raises JSONDecodeError for a bad cache row.

**Tests:**
- `test_retry_after_is_clamped_and_sanitised`, parametrised over 120→60, -5→0, inf→1, nan→1,
  and an HTTP-date→1.
- `test_corrupt_cache_row_is_a_miss`: the HTTP call is made again, the row is repaired, and
  `cached == 0`.
- `test_unknown_model_costs_zero_and_warns` and `test_known_model_does_not_warn`.

**RED:** 6 failed, including `json.decoder.JSONDecodeError` from the corrupt-cache test. The
HTTP-date case already passed. **GREEN:** `41 passed in 0.29s`.

## M3. Pledging

`finn/classify/rules.py`: under the desc `Disclosure under SEBI Takeover Regulations`, text
(subject + summary) matching `pledg|encumb` is classified as `pledging` with subtype None.
Other SAST rows stay `insider_trading/sast`.

**Tests:**
- `test_sast_pledge_disclosure_is_pledging`, with three subjects: create pledge, release of
  encumbrance, and "pledged".
- `test_sast_without_pledge_stays_insider_trading`.

**RED:** 3 failed. **GREEN:** passing. The month fixture has no SAST rows, so eval numbers are
unchanged.

## M4. Alerts link to filings

**Changed**
- `Alert.seq_id: str | None` holds the headline seq_id, and `evaluate_filings` sets it.
- `GET /filings/{seq_id}` accepts a repeatable `subscribed` query param (a `list[Category]`;
  an unknown category returns 422).
- **Choice:** when the param is omitted, `subscribed` defaults to the digest's default
  (`Rules().categories`) instead of the previous empty set. That way a plain link matches the
  default digest card, which is the stated goal. The cost is that there is no way to ask for
  "no subscriptions" through the query string.

**Tests:**
- `test_filing_detail_score_matches_the_digest_card` covers `["results"]`,
  `["mna","litigation"]` and omitted. For the top 10 cards, score and reasons must equal the
  card headline's.
- `test_filing_detail_rejects_unknown_category`.
- `test_filing_alerts_link_to_their_headline_filing`: each filing alert's `seq_id` resolves,
  and its detail score equals the alert value. Non-filing alerts have `seq_id` null.
- The unit test asserts `a.seq_id == "a"`.

**RED:** 3 of the new API tests failed, and the unit test failed with an AttributeError.

## M5. Lookback vs bars loaded

**Changed**
- `/alerts` loads `max(60, lookback + ALERT_SESSIONS + 1)` bars (`HISTORY_BARS = 60`).
  `_completed_history` takes a `bars` argument.
- The volume message is `f"… {rules.lookback}-day average volume"`, so it says "20-day" only
  when lookback is 20.

**Tests:**
- `test_long_lookback_loads_enough_history`: TRENT has 130 sessions (70 at 100 shares, 59 at
  1,000, then 1,500). Lookback 20 gives no alert. Lookback 120 gives exactly one volume alert:
  "TRENT traded 2.8× its 120-day average volume".
- To confirm the test is sensitive, I temporarily reverted the bar count to 60. It then fails
  with `assert [] == [('volume', '2026-11-06')]`.
- `test_volume_message_names_the_lookback` (lookback 10 → "10-day").

## M6. pandas declared

`uv add pandas` added `"pandas>=3.1.1"` to `[project].dependencies`. The uv.lock diff is two
lines (the finn package's dependency list and its requires-dist). The installed version is
unchanged, and no other dependencies were added.

## M7. Committed-seed smoke test

New `tests/test_seed.py` opens backend/seed/finn.sqlite with
`file:…?mode=ro&immutable=1`, so it is read-only and no `-wal`/`-shm` files appear next to the
committed seed. I confirmed with `git status` that it is clean after the run. It asserts:
- the five tables exist;
- there are exactly 18 distinct price symbols, equal to the portfolio's symbols;
- filings > 0;
- no filing has a NULL category.

It passes on the current seed. Running the same function against an empty initialised store
raises AssertionError, so it does catch a bad seed.

## M8. Test rename

`test_digest_default_24h_window_shape` is renamed `test_digest_168h_window_shape`, since it
tests 168h. A new `test_digest_defaults_to_24h` checks that `{}` gives the window
[NOW − 24h, NOW].

## M9. One default-classification helper

`finn/classify/__init__.py` defines `default_classification()`. pipeline.py, llm.py (its
private `_default` is removed), digest.py and eval_classify.py all use it, so the literal now
exists only in the helper. `test_default_classification_helper` pins its fields.

---

## End-to-end check (real seed, not committed)

I created an empty initialised store in the scratchpad (the state llm_smoke and eval used to
leave behind) and booted the app through its lifespan:
```
portfolio dates: Counter({'2026-11-06': 18})          # the Sunday 8 Nov Muhurat bars are gone
alerts window: {'start': '2026-10-31T16:58:42+05:30', 'end': '2026-11-07T16:58:42+05:30'}
  kinds: Counter({'filing': 20, 'volume': 13, 'price': 8})
filing alert seq_ids present: True
digest 24h counts: all 0, latest_filing_at: 2026-11-07T16:58:42+05:30
```
The empty store was seeded. The 24h digest is empty but reports the newest filing, which is
the "nothing in 24h · last filing Fri 7 Nov" case.

## Choices the brief left open

1. **I3 result shape.** `ingest_filings` always returns `IngestResult` and never raises
   `NSEUnavailable`. When every symbol fails, the result has every symbol in `failed`.
   `refresh()` turns each failed symbol into one `errors` entry, so an all-403 run reports 18
   entries.
2. **I3 malformed rows** count as data problems, not fetch failures. A symbol whose fetch
   succeeded but had skipped rows still allows `filings_as_of` to advance. The count is in the
   summary as `filings_skipped`, not in `errors`.
3. **I3 missing price symbols** are listed in the summary as `prices_missing` and also added
   to `errors` when other bars did arrive. A permanently delisted symbol would therefore make
   refresh exit 1 every run.
4. **I2 warning scope.** The missing-seed warning fires when a seed copy is needed (the store
   is missing or empty) and the seed is absent. A populated store with no seed is silent,
   because the seed is irrelevant there.
5. **I4 session-in-window test** is by date: `start.date() ≤ bar.date ≤ end.date()`, capped at
   the last 5 sessions up to `end`.
6. **M4 default** for an omitted `subscribed` is the digest default, as described under M4
   above.
7. **I5 text** for the rule-derived subtypes includes `nse_desc`, as the DESC_MAP path does.
   None of the ambiguous descs contain role or rating words, so this only helps with descs the
   rules don't know.

## Concerns

- The committed seed still holds the Sunday 8 Nov Muhurat bars, and its 64 defaults predate
  M1 and M3. The API already filters weekend bars, and the controller's re-seed will pick up
  the rest.
- The `/filings/{seq_id}` default changed from no subscriptions to the digest default (see M4).
  No test or caller relied on the old behaviour, but the frontend plan should know.
