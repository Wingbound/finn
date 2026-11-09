# Task 9 report

## Implemented
- finn/ingest/screener.py: parse_quarters (stdlib html.parser), fetch_quarters (httpx, browser UA, 30 s; live only), screener_url.
- scripts/eval_results.py: --offline / --db; per-pair comparison (1% or INR 1 cr), basis-equality rule (R5), indas PBT + associates/JV share / 1e7, Markdown table + per-metric rates + misses; main() returns 0.
- scripts/refresh.py: after classify, one NSEClient runs financials (always), then people and briefs (only with a router), each never-raise; summary gains "financials" and "enrich"; failures appended to errors as "financials: SYM: why", "people: SEQ: why", "briefs: SEQ: why".
- docs/DESIGN.md (routing row, gold set, Hosting note), docs/EVALS.md section 2 with offline table and the marked placeholder.

## TDD
RED: `uv run pytest -q tests/test_screener.py tests/test_eval_results.py tests/test_refresh.py` -> 2 collection errors (ImportError: cannot import name 'eval_results'; no finn.ingest.screener).
GREEN: `uv run pytest -q` -> 321 passed in 2.09s. `uv run ruff check .` all passed; `ruff format --check .` 62 files formatted.

## Tests added
test_screener.py (4), test_eval_results.py (4), test_refresh.py (4 new + autouse stub fixture).
Offline eval: TATASTEEL 4/4 match; IDFCFIRSTB, BAJFINANCE skipped: basis mismatch.

## Files
backend/finn/ingest/screener.py, backend/scripts/eval_results.py, backend/scripts/refresh.py, backend/tests/{test_screener,test_eval_results,test_refresh}.py, docs/DESIGN.md, docs/EVALS.md

## Self-review / concerns
- Existing refresh tests now have an autouse fixture stubbing ingest_financials/enrich_people/enrich_briefs (otherwise respx-unmocked NSE calls would pollute errors); the new tests restore the real ingest_financials.
- If NSEClient() construction itself fails, errors gets one "financials: Type: msg" entry and people/briefs are skipped.
- Live eval for non-first-load symbols depends on screener pages; fetch errors are reported as skipped rows, not raised.
- Bank/nbfc comparisons are untested offline (basis mismatch in fixtures); first exercised in the live run.

## Fix round 1
Changes:
1. refresh.py: classify_pending now runs (result in `classify`) before financials/people/briefs. New test test_enrichers_see_filings_classified_in_the_same_run (real enrich_people, FakeRouter, same-run management_change filing, pre-seeded doc text); verified it fails with the old ordering.
2. screener.parse_quarters isolates `<section id="quarters">` (falls back to whole input) and parses only its first `<table>`. New multi-section page test. Deviation: the real fixture already has Mar 2025/Mar 2026 quarter columns, so the decoy sections use Mar 2019/2020/2021 headers; the test also asserts Mar 2025 Sales is not the decoy 999.
3. Tests: every PAIRS key exists in build_card metrics for indas/bank/nbfc fixtures; compare() on IDFCFIRSTB with basis forced to standalone compares interest_earned, pbt, pat (none "missing value").
4. DESIGN.md: HF Space / port 7860 / NEXT_PUBLIC_API_URL / Gemini-PDF day-2 / HF Space deploy lines updated; robustness paragraph rewritten (snapshot + out-of-band refresh); Hosting note moved under section 2. test_refresh.py docstring now says `fin_env`.
Commands/output:
- `uv run pytest -q tests/test_refresh.py tests/test_screener.py tests/test_eval_results.py` -> 27 passed in 0.77s
- `uv run pytest -q` -> 325 passed in 2.14s
- `uv run ruff check .` -> All checks passed!; `uv run ruff format --check .` -> 62 files already formatted
