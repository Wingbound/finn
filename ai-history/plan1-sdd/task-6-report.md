# Task 6 report
Implemented finn/classify/llm.py (classify_batch_llm, pydantic-validated reply, per-item/whole-batch defaults) and finn/classify/pipeline.py (classify_pending: rules, then LLM or default, persists, returns counts).
Tests: backend/tests/test_classify_llm.py (7 tests: batches of 20, compact prompt, bad output, malformed reply, LLMError, rules-first, router None).
RED: ModuleNotFoundError finn.classify.llm. GREEN: 7 passed; full suite passes; ruff clean.
Choices: summary truncation reuses rules.SUMMARY_CHARS (400); a malformed reply (ValidationError) defaults the batch; duplicate ids in a reply: last wins. Commit uses the instructed Opus 5.5 trailer.

## Fix round 1
Changes (finn/classify/llm.py): removed whole-reply pydantic models; envelope checked leniently (`items` must be a list, else batch default); each item validated by `_parse_item` (int id stringified, bad/null category -> that item defaults, non-string subtype -> None with valid category kept as by="llm"). complete_json now caught for `(LLMError, ValueError)`.
Tests added: test_one_bad_item_defaults_only_itself, test_items_not_a_list_defaults_batch, test_valueerror_defaults_batch.
Command: `uv run pytest tests/test_classify_llm.py -q` -> 10 passed; full suite `uv run pytest -q` -> 76 passed; ruff clean.
