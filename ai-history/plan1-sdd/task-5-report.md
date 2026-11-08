# Task 5 report
Implemented finn/llm/{__init__,router,providers,costs}.py, ROUTES + route_for + env-overridable model IDs in config.py, scripts/llm_smoke.py, tests/test_llm_router.py (10 tests).
Models (UNVERIFIED, from public docs via WebFetch 2026-11-08): classify/oneliner llama-3.1-8b-instant; extract_pdf/reason/bio gemini-3.8-flash; extract_transcript gemini-3.5-flash-lite. Pro (gemini-3.1-pro-preview) has no free tier so reason=Flash. Env overrides: FINN_MODEL_<TASK>.
Prices: Gemini from pricing page (Flash promo 0.75/3.75 until 2026-12-31, then 1.50/7.50); Groq llama-3.1-8b price is "contact sales" so 0.05/0.08 is an approximation.
TDD: tests written with the module absent (import failure RED), then 10 passed. Full suite: 62 passed; ruff check clean.
Live smoke (Step 3) deferred: run `uv run python scripts/llm_smoke.py` when keys exist.
Notes: missing key raises LLMError("missing GROQ_API_KEY") before HTTP; cache hits log cached=1 with 0 tokens; 4xx other than 429 raise immediately; retry sleeps via patchable router._sleep. `ruff format --check` fails on pre-existing files (classify), not touched.
Commit trailer used Sonnet 5.5 per the latest attribution instruction (implementer-instructions said Opus 5.5).

## Fix round 1
1. config.py: ROUTES annotation now dict[str, Literal["groq","gemini"]]; route_for docstring marks it the public (provider, model) accessor.
2. parse_gemini raises LLMError with blockReason / finishReason (no retry). LLMError moved to providers.py, re-exported by router. Tests: test_gemini_safety_block_raises_clear_error (2 shapes, asserts 1 call, no sleeps).
3. Invalid JSON after a 200 now logs an llm_calls row (cached=0, tokens) before raising; nothing cached. Calls that never got a 200 stay unlogged (my choice). Test: test_invalid_json_still_logs_usage.
4. Gemini output_tokens = candidatesTokenCount + thoughtsTokenCount. Test: test_gemini_thinking_tokens_count_as_output.
Run: `uv run pytest tests/test_llm_router.py -q` -> 14 passed; full `uv run pytest -q` -> 66 passed; ruff check clean.
