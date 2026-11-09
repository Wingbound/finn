# Task 8 report
Implemented finn/enrich/brief.py (make_brief, enrich_briefs, attach_briefs, CATEGORY_TERMS), Fact/Brief/Story.brief in models.py, attach_briefs in digest.py, tests/test_brief.py (17 tests).
Design: make_brief lets LLMError propagate (enrich_briefs records it in failed, saves nothing). Invalid one-liner -> NSE-summary fallback (saved); none -> {"brief": null, "reason": ...} counted empty. make_brief takes an optional `category` kwarg to select window terms. attach_briefs tries headline then members, skips corrupt rows (ValidationError, warning log).
TDD: RED = `uv run pytest tests/test_brief.py -q` -> ModuleNotFoundError finn.enrich.brief. GREEN = `uv run pytest -q` -> 306 passed; ruff check and format clean.
Self-review: one test initially expected "Alpha Ltd." to end a sentence; the splitter treats "ltd." as an abbreviation, so I changed the fixture to "Limited". Fallback of a brief that has no valid reply and no summary saves a null row (not retried).
Concerns: for a PDF that is oversize (cached ""), text falls back to the NSE summary. A non-LLM crash (generic Exception) is not saved, so it retries every refresh.

## Fix round 1
Changes: added grounding.phrase_in_text (word-boundary, min_words). Non-digit fact values need >=3 normalized chars and phrase_in_text; digit values still use numbers_grounded. Quote needs phrase_in_text with 4 words minimum.
Tests: new brief tests (tiny/partial facts "a","in","ab","ratin" dropped, "CRISIL AA+" kept; "the" quote dropped, long quote kept) and phrase_in_text unit test. Note: "ltd" itself is 3 chars and present in the subject, so it is legitimately kept under the ruling; test uses "ab" instead.
Command: uv run pytest -q -> 309 passed; ruff check/format clean.
