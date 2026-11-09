# Task 4 report
Implemented: financials table + upsert/get/stored_urls/latest helpers (db.py); FinancialsResult, ingest_financials, card_for, module-level _sleep (enrich/results.py); tests/fakes.py (FakeNSE, tatasteel_fake); tests/test_results_store.py (9 tests).
TDD: RED = `uv run pytest -q tests/test_results_store.py` -> 9 errors (AttributeError, no ingest_financials/_sleep). GREEN = full suite `243 passed`; ruff check and format clean.
Notes: ingest overrides parsed q.basis with the NSE listing's basis (authoritative); card_for with explicit period_end tries consolidated then standalone; BLE001 noqa on the per-symbol catch. `from tests.fakes import` works without tests/__init__.py.
Concern: db.py now imports finn.ingest.xbrl (QuarterFinancials); no cycle found.

## Fix round 1
Changes: removed basis override; a document/list basis mismatch skips the target and records "<period_end> basis mismatch: list X, document Y" in failed; rows are stored under the requested symbol (model_copy). Tests: rewrote fallback and standalone tests using synthetic standalone XML (precise element replace); added basis-mismatch and requested-symbol tests.
Command: `uv run pytest -q tests/test_results_store.py` -> 11 passed; full suite `uv run pytest -q` -> 245 passed; ruff check/format clean.
