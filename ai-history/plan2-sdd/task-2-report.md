# Task 2 report
Implemented: nse.py refactor (_get with optional check callback, _get_json, INTEGRATED_URL, fetch_integrated_financials, fetch_bytes); new finn/ingest/xbrl.py (detect_format, parse_filing_list, parse_xbrl, models, XbrlError). R4 audited mapping applied in both places.
TDD: RED `uv run pytest -q tests/test_xbrl.py tests/test_nse.py` -> ModuleNotFoundError finn.ingest.xbrl. GREEN `uv run pytest -q` -> 223 passed; ruff check and format clean.
Files: backend/finn/ingest/nse.py, backend/finn/ingest/xbrl.py, backend/tests/test_xbrl.py, backend/tests/test_nse.py.
Self-review: fetch_announcements error message kept as "NSE announcements for X failed: <reason>". fetch_bytes downloads fully before size check (content-length checked first, then body). Extra test for audited mapping added.
Concerns: _get has a small extra `check` callback param beyond brief signature; fetch_bytes does not stream.
