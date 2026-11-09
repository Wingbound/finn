# Task 6 report: cited snapshot and bull/bear

Implemented finn/research/synthesis.py: facts_block (code-built, None lines skipped, flags included), snapshot(router, sources, guard=None), bull_bear(router, sources, ledger, trajectory, health, guard=None). Per-point validation: type check, <=30 words, known source_id, locate() verbatim, numbers_grounded against quote + FACTS (empty FACTS for snapshot). guard counters points_proposed (len of raw list) and points_kept (after cap 4/3). LLMError gives None / ([], []). models.py gained Point and Snapshot.

Tests: tests/test_research_synthesis.py, 6 tests (facts block, real vs invented quote, None/LLMError, FACTS number kept vs invented dropped, cap 3 + >30 words, bad types/unknown source).
RED: `uv run pytest -q tests/test_research_synthesis.py` -> ModuleNotFoundError: No module named 'finn.research.synthesis' (1 error in collection).
GREEN: full `uv run pytest -q` -> 498 passed; ruff check and format --check clean.

Files: backend/finn/models.py, backend/finn/research/synthesis.py, backend/tests/test_research_synthesis.py.

Self-review: sources are not mutated (model_copy with sliced pages). Quotes are validated against the full source, not just the sliced prompt pages. Snapshot keeps 1 point if only one survives (brief says keep 2-4; never padded).
Concerns: facts_block shows extra lines beyond the examples (net profit CAGR, WC days, ROCE) when non-None. Ledger line omitted if counts is empty. "Operating margin"/"Debt to equity" use :g formatting (0.06, 0.97).
