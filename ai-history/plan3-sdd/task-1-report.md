# Task 1 report

Implemented in backend/finn/ingest/screener.py: parse_table (generalises parse_quarters; parse_quarters now delegates), label cleanup (cut at 2+ spaces), search, fetch_company, parse_documents, parse_name, ScreenerError, SCREENER, module-level _http() helper (browser UA, 30s, closed after use when owned).
Deviation: _section returns "" when a full page (has any <section) lacks the requested id, so a missing profit-loss in a consolidated page is empty instead of silently parsing the first table of the page; bare fragments (Plan 2 fixtures) still parse whole.

Tests (backend/tests/test_screener.py): 10 new tests plus the existing ones. Hard-coded Mar 2026 Sales 14748.0, OPM % 19.0.
RED: `uv run pytest -q tests/test_screener.py` with the old screener.py -> ImportError: cannot import name 'ScreenerError' (collection error).
GREEN: `uv run pytest -q` -> 386 passed; ruff check and format --check clean.
Commit: cdd81fb on feat/pull-research.

Self-review: stdlib only; &amp; unescaped by convert_charrefs plus html.unescape. Annual reports sorted newest first; concalls keep page order (newest first on screener). The implementation was written before the tests were run (RED was shown by stashing the impl).
Concerns: search params q/v/fts are assumed from the spike; the "Transcript"/"PPT" matching is by link text. CFO/EBITDA is in the cash-flow section, not ratios.
