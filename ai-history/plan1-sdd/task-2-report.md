# Task 2 report
Implemented finn/models.py (Category, Filing w/ aware->IST validator, Classification, PriceBar) and finn/db.py (all brief interfaces; llm_cache/llm_calls tables per controller ruling; filed_at stored as IST ISO; upsert_filings INSERT OR IGNORE, count via total_changes; upsert_prices refreshes bars, returns new-row count; window inclusive both ends).
Tests: backend/tests/test_db.py (7 tests incl. naive-rejection, UTC->IST window, llm tables). RED: ImportError cannot import name 'db' from 'finn'. GREEN: 10 passed (full suite), ruff clean.
Self-review: no issues. Concern: none (upsert_prices updates existing bars rather than ignoring; brief only fixed return count).
