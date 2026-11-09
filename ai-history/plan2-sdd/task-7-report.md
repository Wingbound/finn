# Task 7 report

## Implemented
- enrich/grounding.py: normalize, name_in_text, grounded_sentences (truncation rule in docstring), numbers_grounded (token-set match, so "500" does not match "5000").
- enrich/people.py: PEOPLE_TERMS, SYSTEM_PROMPT, extract_people, enrich_people, attach_people (incoming first, else first-appearance order, dedupe by normalized name).
- enrich/__init__.py: EnrichResult (R2). nse.PayloadTooLarge (R9) raised by fetch_bytes; get_doc_text caches "" on it.
- models: PersonChange, Story.people. db: enrichments table, save_enrichment, get_enrichments, filings_missing_enrichment (returns Filing+Classification). digest: attach_people beside attach_results.
- tests/fakes.py: FakeRouter (R10).
- Sentence splitter does not split after Mr/Mrs/Ms/Dr/Smt (otherwise "Mr." became its own, trivially grounded, sentence).

## Tests
test_grounding.py, test_people.py (new), plus oversize tests in test_pdftext.py and test_nse.py.
RED: `uv run pytest -q tests/test_grounding.py tests/test_people.py ...` -> ImportError (finn.enrich.people missing), 2 collection errors.
GREEN: `uv run pytest -q` -> 282 passed; ruff check and format --check clean.

## Self-review
- Fixed a test bug (category kwarg) found on first green run.
- Failures (LLMError, NSEUnavailable incl. non-oversize) save nothing; oversize PDF gives "" -> saved as empty "no text".
## Concerns
- Profile sentences split on ". " inside initials (e.g. "C.P. Menon") may fragment, but each fragment must still be verbatim in the filing, so no fabrication risk.
- Whole-text grounding for names: a name appearing anywhere in the filing (even as a non-changing party) passes; role/change correctness is the LLM's.

## Fix round 1
Changes: (1) split_sentences merges across Mr/Mrs/Ms/Dr/Shri/Smt/Prof/Ltd/Pvt/Co/No/viz/i.e/e.g and capital initials; kept sentences need >= 4 words. (2) Field types validated; enrich_people has per-filing catch-all (failed[seq] = "Type: msg"). (3) role and effective kept only if in filing text. (4) filter test now pre-caches text and asserts no router/client calls. (5) name_in_text: >= 2 tokens, word-boundary regex.
Tests added: splitter, bare-honorific, word boundary, malformed types, bad replies/RuntimeError with other filings processed, role grounding, filter test; Balan test asserts exact string.
Note: ruling's example role "Chief Executive Officer" IS in the Voltas text (CEO of Voltbek), so the test uses "Chief Financial Officer" instead.
Command: uv run pytest -q -> 288 passed; ruff check and format --check clean.
