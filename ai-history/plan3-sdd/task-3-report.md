# Task 3 report

Implemented finn/research/docs.py (DocClient, DocError, call_quarter, pdf_pages, get_pages, collect_sources), Source model in models.py, doc_pages table + get_doc_pages/save_doc_pages in db.py, tests in backend/tests/test_research_docs.py.

TDD: RED: `uv run pytest -q tests/test_research_docs.py` -> ImportError: cannot import name 'docs' from 'finn.research'. GREEN: `uv run pytest -q` -> 412 passed; ruff check and format --check clean.

Notes: DocClient retries (2, via patched-able _sleep) on 5xx/429/transport errors; other 4xx fail immediately. max_bytes checked after download. Transcript with no non-blank text is skipped with a note. Empty AR text also gives a note. call_quarter maps call month: Jan-Mar Q3 FYy, Apr-Jun Q4 FYy, Jul-Sep Q1 FY(y+1), Oct-Dec Q2 FY(y+1).
Concerns: max_bytes is not streamed, so an oversized body is fully downloaded first. A cached AR keeps whatever cut it was first fetched with.

## Fix report (round 1)

Changes: collect_sources wraps each source's whole work (label parse, fetch, extraction) in `except Exception` (noqa BLE001) and notes `"{label} skipped: {Type}: {msg}"` (label = date, "annual report" or "unknown"). call_quarter still raises ValueError (docstring says so). Tests added: bad date "Sometime", row missing date, AR missing year, httpx.InvalidURL from client, call_quarter("Jan 2027") == "Q3 FY27".
Command: `uv run pytest -q tests/test_research_docs.py` -> 15 passed; full `uv run pytest -q` -> 414 passed; ruff check "All checks passed!"; ruff format --check "67 files already formatted".
