# Task 4 report: grounded guidance extraction

Implemented: Citation/Promise in models.py; research/cite.py (locate: hint page, all pages, adjacent pairs cited to first page, min 6 words; tagged_text default 90_000, page-boundary truncation); research/guidance.py (extract_promises with prompt per ruling, validation order type-check, locate, ground targets via numbers_grounded(f"{v:g}"), enum scrub, dedupe by normalize(quote); never raises; [] on LLMError / bad shape; capped at MAX_PROMISES=8).

Tests: 15 new (test_research_cite.py, test_research_guidance.py), full suite 429 passed; ruff check and format clean.

TDD: RED = tests run with impl files moved aside: "ModuleNotFoundError: No module named 'finn.research.guidance'", 2 collection errors. (Impl was written before the first run, so RED was shown by removing it.) GREEN = `uv run pytest -q` -> 429 passed.

Files: backend/finn/models.py, backend/finn/research/{cite,guidance}.py, backend/tests/test_research_{cite,guidance}.py.

Self-review: bool and non-numeric targets treated as None; made_in falls back to "" if quarter is None (Promise.made_in is str). Items whose topic is missing are dropped. Hint page is 1-based, out-of-range hints ignored.

Concerns: a target that is not in the quote only demotes to qualitative (per ruling); metric is kept even then. Percent-style targets like 22.5 vs "22.50" are matched by token text, so "22.50" in a quote would fail grounding for 22.5.

## Fix round 1
Changes: (1) cite.locate: new _found() rejects an occurrence if the same sentence's prefix before the match holds a negation token (whole word); other occurrences/pages/pairs still searched. (2) grounding._numbers strips period labels (FY\d{2,4}, Q[1-4], H[12], 9M, [1-4]Q, case-insens) before extracting numbers. (3) guidance: kind = quantitative iff a grounded target remains; unit None when no targets.
Tests added: 4 negation tests (cite), 1 period-label test (grounding), 1 kind/targets test (guidance, both directions).
Commands: `uv run pytest -q tests/test_research_cite.py tests/test_research_guidance.py tests/test_grounding.py` -> "32 passed in 0.10s"; `uv run pytest -q` -> "435 passed in 2.36s"; `uv run ruff check .` -> "All checks passed!"; `uv run ruff format --check .` -> "71 files already formatted".
