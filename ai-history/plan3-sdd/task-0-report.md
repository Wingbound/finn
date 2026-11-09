# Task 0 report

## Implemented
- digest.py: `_card_or_none` renamed `card_or_none`; attach window now -4d..+45d (story filed_at minus card filed_at).
- api/main.py: `/results/{symbol}` uses `card_or_none`, so a corrupt row gives 404 "no results on file".
- llm/router.py: `_exhausted_until` keyed by (provider, model).

## Tests
Added test_results_endpoint_corrupt_row_is_404, test_quota_on_one_model_keeps_sibling_model_usable, test_same_quarter_story_45_days_later_gets_card, test_story_60_days_later_gets_no_card; moved far-apart story date to 2027-01-15.

## TDD
RED: `uv run pytest -q tests/test_api.py tests/test_digest_results.py tests/test_llm_router.py` -> 3 failed, 86 passed (corrupt 404 json decode/500, 45-day attach, sibling model "all models failed: ... quota exhausted"). The 60-day test passes pre-change by design (regression guard).
GREEN: `uv run pytest -q` -> 377 passed; ruff check and format --check clean.

## Files
backend/finn/digest.py, backend/finn/api/main.py, backend/finn/llm/router.py, tests/test_api.py, tests/test_digest_results.py, tests/test_llm_router.py

## Self-review
No remaining references to the old names. Sibling-model test patches router_mod.chain_for.

## Concerns
None.
