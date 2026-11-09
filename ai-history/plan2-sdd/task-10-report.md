# Task 10 report: quota-aware 429 handling

Commit 3a9b6d8 on feat/push-enrichment.

## Implemented
- router.py: `_now()`, private `_QuotaExhausted(LLMError)` with `retry_after`, `_quota_wait()` (finite number > 60 -> quota; absent, HTTP-date, inf/nan, <=60 -> pacing).
- `_request` raises `_QuotaExhausted` on such a 429 with no sleep.
- `complete_json` marks `_exhausted_until[provider] = _now() + retry_after`, records "<p>/<m>: quota exhausted (retry in Ns)", moves on.
- Exhausted providers are skipped (no HTTP) on later calls; expired entries pruned each call.
- `usable` (which sets the full-retry budget for the last model) now excludes exhausted providers. "missing KEY" error is raised only if no provider has a key (`keyed`). If all keyed are exhausted: "all models failed: ...".
- Cache lookups happen before the skip, so unaffected.
- DESIGN.md sentence extended.

## Tests
Added the 5 new tests (the pacing one, test 4, already existed unchanged) plus the non-numeric test.
Full: `cd backend && uv run pytest -q` -> 373 passed; ruff check and format --check clean.

TDD RED: `uv run pytest -q tests/test_llm_router.py` -> 4 failed, 41 passed (quota tests; e.g. "gave up after 3 retries: HTTP 429" instead of quota exhausted).
GREEN: same command after implementation, full suite 373 passed.

## Files
backend/finn/llm/router.py, backend/tests/test_llm_router.py, docs/DESIGN.md.

## Self-review / concerns
- Existing parametrized case `("120", 60.0)` in test_retry_after_is_clamped_and_sanitised contradicts the new rule (120 > 60 is quota). Changed it to `("60", 60.0)`; the "capped" path is now only reachable at exactly 60 (clamp stays as defensive code).
- docs/EVALS.md had uncommitted changes before my work; left unstaged.
- Exhaustion state is per-router instance, as specified.
