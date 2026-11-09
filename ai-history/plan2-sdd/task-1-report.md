# Task 1 report: cross-provider fallback chains

Implemented FALLBACKS + chain_for in config.py (bio -> Groq gpt-oss-120b), complete_json loop in router.py
(cache lookup across chain; skip missing keys; retries=MAX_RETRIES for last usable model else 1; any LLMError
moves on; last_model; "missing KEY" if none usable else "all models failed: ..."), _request(retries=).
Tests: 7 new + 1 dedupe test; 4 Plan 1 tests (persistent_5xx, invalid_json x2, gemini safety) changed Settings only
(per R1), assertions untouched.
RED: `uv run pytest tests/test_llm_router.py -q` -> ImportError: cannot import name 'chain_for'.
GREEN: `uv run pytest -q` -> 207 passed; ruff check and format --check clean.
Files: backend/finn/config.py, backend/finn/llm/router.py, backend/tests/test_llm_router.py.
Concerns: none. Note a 4xx from a primary also falls through (any LLMError), per brief.
