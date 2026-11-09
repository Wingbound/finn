# Task 8 report

Commit 9f997b5 on feat/pull-research.

## Implemented
- `Dossier.guard: dict = {}`; `extract_promises(router, source, guard=None)` counts promises_proposed/kept; `build_dossier` creates one guard dict, passes it to guidance, snapshot, bull_bear, and stores it (P3-R11).
- `backend/scripts/eval_research.py` (`--db PATH`, default DB_PATH, main() returns 0): re-locates every non-FACTS citation (page must match), checks FACTS quotes against recomputed facts_block (normalised); Markdown table per dossier plus total row (verified/total, ledger distribution, computed/judged, guard kept/proposed, drop rates, calls, usd, seconds); failures listed as `symbol | field | source_id p{page} | quote[:80]`.
- Docs: EVALS.md section 4 (method, limits, "Live results: pending (controller)"); DESIGN.md new "Pull: research dossiers" subsection (no existing Pull section existed, so placed before Materiality score).

## Tests
`tests/test_eval_research.py` (5): guard recorded, old payload gets empty guard, 100% verification incl. a FACTS citation, report columns/guard counts, corrupted ledger quote reported. Reuses helpers from tests/test_research_pipeline.py.

## TDD
RED: `uv run pytest -q tests/test_eval_research.py` -> `ImportError: cannot import name 'eval_research' from 'scripts'`, 1 error.
GREEN: `uv run pytest -q` -> 530 passed; ruff check and format --check clean.

## Files
backend/finn/models.py, finn/research/guidance.py, finn/research/pipeline.py, scripts/eval_research.py, tests/test_eval_research.py, docs/DESIGN.md, docs/EVALS.md.

## Self-review / concerns
- The test module imports helpers and the `seeded` fixture from another test module (works, slightly coupled).
- A FACTS citation in a dossier lacking trajectory/health/ledger counts as a failure.
- Promise drop rate counts dedup and the 8-item cap as drops, not just unverifiable quotes.
- DESIGN.md budget/grading wording follows the brief; I did not re-check it against code.
