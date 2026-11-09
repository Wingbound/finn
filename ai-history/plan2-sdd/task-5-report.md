# Task 5 report

Implemented: Story.results field; attach_results(conn, stories) in finn/digest.py (category results, subtype not intimation, card filed_at within 4 days; per-symbol cache, one card_for per symbol per call); build_digest calls it on shown + all routine stories; GET /results/{symbol} (upper-cased, 404 "no results on file").

RED: `uv run pytest -q tests/test_digest_results.py tests/test_api.py` -> 7 failed, 26 passed (attribute/404/KeyError 'results').
GREEN: `uv run pytest -q` -> 252 passed; ruff check and format --check clean.

Files: backend/finn/{models,digest,api/main}.py, backend/tests/{test_digest_results,test_api}.py. Commit 2edd7e2.

Self-review: first non-results test used invalid category "other"; fixed to press_release. Attach step is a separate function ready for people/brief.
Concerns: none. card_for is called once per symbol even when the first story fails the date check (cached None/card reused).
