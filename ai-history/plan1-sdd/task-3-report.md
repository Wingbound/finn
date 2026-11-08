# Task 3 report
Implemented finn/ingest/nse.py (NSEUnavailable, NSEClient, parse_announcement, ingest_filings), scripts/record_fixtures.py, real fixtures (RELIANCE, M&M, TRENT, portfolio_month = 323 items from 18 symbols, 08-10-2026..08-11-2026), tests/test_nse.py (8 tests), tests/conftest.py (shared `conn` fixture).
Retry: max_retries = total attempts (3), backoff 0.5/1/2 via module-level `_sleep` (patched in tests); re-warm on 401/403; non-JSON content-type/body/non-list = failure.
ingest_filings is atomic: fetch all, then upsert + set filings_as_of (IST ISO now).
RELIANCE.json contains seq_ids 106837394, 106837395, 106837406, 106837413.
TDD: RED = ImportError (finn.ingest.nse missing) with module removed; GREEN = full suite 18 passed, ruff clean. (Impl was written before the RED run; RED was verified afterwards by temporarily removing the module.)
