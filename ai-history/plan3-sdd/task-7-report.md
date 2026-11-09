# Task 7 report

## Implemented
- finn/research/pipeline.py: build_dossier (injectable clients and clock, deadline checks before each LLM stage, per-stage failure notes, cost delta from router.stats()). ScreenerError propagates.
- finn/models.py: Dossier and public() (drops Source.pages). finn/db.py: dossiers table, save/get/list_dossiers (stored with pages).
- finn/api/main.py: GET /research, /research/search (q min_length 1 -> 422), /research/{sym} (404 with build link), /research/{sym}/source/{id}/{page}, /research/{sym}/build (SSE; worker thread with own connection and LLMRouter, queue, sentinel; 10 minute cache).
- scripts/research.py: CLI, always exits 0 (also reports a per-symbol crash as a line).

## Tests
`uv run pytest -q` -> 512 passed; ruff check and format --check clean.
RED: `uv run pytest -q tests/test_research_pipeline.py tests/test_api_research.py` -> collection error `ModuleNotFoundError: No module named 'finn.research.pipeline'`.
GREEN: full run above (512 passed). A first run had one test fail (my wrong transcript-count assumption: the fixture lists 34 transcripts/15 ARs) and the 404 body shape; both fixed.

## Files
finn/research/pipeline.py, finn/models.py, finn/db.py, finn/api/main.py, scripts/research.py, tests/test_research_pipeline.py, tests/test_api_research.py. Commit 45037fb.

## Self-review / concerns
- "Found n transcripts" counts every screener concall with a transcript link (34 for PERSISTENT), though only 4 are read.
- FakeRouter lacks stats(); build_dossier falls back to zero cost in that case.
- The 404 uses JSONResponse so the body is exactly {"detail","build"}; route has response_model=None.
- Bull/bear is skipped with a note when ledger or financials are missing.
- Progress "Writing snapshot and bull/bear" is emitted even if the deadline then skips them.
- Worker thread is a daemon; an abandoned client does not cancel the build (it still saves).
- CLI not run live.
