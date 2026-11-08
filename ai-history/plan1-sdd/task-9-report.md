# Task 9 report: HTTP API

Implemented finn/digest.py (build_digest + helpers), finn/api/{__init__,deps,main}.py, db.get_filing (+test), tests/test_api.py (9 tests).
Routes: GET /health, GET /portfolio, POST /digest, POST /alerts, GET /filings/{seq_id}. Rulings 1-8 followed.

TDD note: I wrote implementation before running the tests, so no clean RED run was captured (process lapse). One test failed on first run (float 110.00000000000001 vs 110.0, test-data bug), fixed.
GREEN: `uv run pytest -q` -> 128 passed, no warnings. `uv run ruff check .` clean.

Choices: Settings env var for db_path is DB_PATH (no prefix). Narrow filterwarnings in pyproject for starlette TestClient "Using httpx" warning (httpx2 install was blocked by the permission classifier). DigestRequest subscribed defaults to Rules().categories; naive start/end are treated as IST. If only `end` is given, start = end - hours.

Step 3 (temp DB in scratchpad, DB_PATH env, not committed), head of POST /digest:
{"window":{"start":"2026-10-08T00:00:00+05:30","end":"2026-11-08T23:59:59+05:30"},"as_of":null,"counts":{"shown":82,"routine":114,"hidden":29,"filings":323},"stories":[{"id":"TATASTEEL:results:106852180","symbol":"TATASTEEL","company":"Tata Steel Limited","category":"results","subtype":"results","score":100,"tier":"critical",...

## Fix round 1
- DigestRequest.hours bounded 0 < hours <= 24*366; validator raises when end < start; handler returns 422 when start-only lies after now.
- Rules: volume_multiple (0,100], price_move_pct (0,100], lookback 5..250; SymbolOverride non-None fields (0,100]. Defaults unchanged.
- digest.py had no line over 100 chars (ruff clean).
- Tests added: test_digest_rejects_bad_windows, test_alerts_reject_out_of_range_rules (422s).
- `uv run pytest -q` -> 130 passed; `uv run ruff check .` -> All checks passed.
