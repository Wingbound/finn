# SDD ledger — plan: docs/superpowers/plans/2026-11-09-plan2-push-enrichment.md

Spec: docs/DESIGN.md (approved design). Branch: feat/push-enrichment (from main dbfa7f7). Plan + fixtures commit: 6ba29cc.

## Pre-flight scan

| pair / task | produces → consumes | finding |
|---|---|---|
| T1 self | the chain retries 1× for non-last models vs "every Plan 1 router test unchanged" | CONFLICT → R1 |
| T2→T4 | fetch_integrated_financials, fetch_bytes, parse_filing_list, parse_xbrl(format_hint) → ingest_financials | consistent |
| T2→T6 | fetch_bytes raises NSEUnavailable → get_doc_text propagates NSEUnavailable | consistent |
| T2 self | parse_xbrl audited "Audited"/"Unaudited" vs list rows "Un-Audited" | AMBIGUITY → R4 |
| T3→T4 | build_card(cur, prev, year_ago, sources), quarter_end_shift → ingest/card_for | consistent |
| T4→T5 | card_for → (card, filed_at) → attach rule uses filed_at | consistent |
| T4→T5/T9 | FakeNSE double is used by three test files | DUPLICATION RISK → R3 |
| T5/T7/T8 | each modifies models.Story + digest.build_digest (attach_*) | sequential edits; consistent if each adds its own field and attach call |
| T6→T7/T8 | get_doc_text, relevant_window → people/brief | consistent |
| T7→T8 | grounding.*, save/get_enrichments, filings_missing_enrichment (tuples, fixed in plan) → brief | consistent after plan fix |
| T7/T8 | EnrichResult return type named in both, home undefined | GAP → R2 |
| T7/T8/T4→T9 | enrich_people / enrich_briefs / ingest_financials → refresh stages | consistent |
| T9 self | offline eval: IDFC/BAJ fixtures are standalone, screener fixtures consolidated | GAP → R5 |
| T6/T7 fixtures | pdf/*.txt was extracted with PyMuPDF in the spike; runtime uses pypdf | note → R6 |
| T1, T3, T5, T6, T8 self | tests vs code vs files | consistent |

## Rulings

- Ruling R1 (T1): "last in chain" means the last *usable* model (provider key set). Plan 1 retry/backoff tests (e.g. test_persistent_5xx_raises_after_backoff, retry-after) may change only their Settings, to `gemini_api_key=""`, so they exercise the single-model path; their assertions stay unchanged — keeps Plan 1 retry semantics pinned without weakening them — cost if wrong: a test-fixture edit.
- Ruling R2 (T7/T8): `EnrichResult` (dataclass: done, empty, failed) lives in `finn/enrich/__init__.py`; T7 creates it and T8 imports it — one shared type, no circular import via people.py — cost if wrong: a move.
- Ruling R3 (T4/T5/T9): the FakeNSE test double lives in `backend/tests/fakes.py` (T4 creates it; T5/T9 import `from tests.fakes import FakeNSE`) — avoids three copies — cost if wrong: a move.
- Ruling R4 (T2): audited maps "Audited" → True, "Un-Audited"/"Unaudited" → False, anything else → None, in both parse_filing_list and parse_xbrl — the list and the XBRL spell it differently — cost if wrong: trivial.
- Ruling R5 (T9): eval_results compares a pair only when the screener page's basis equals the card's basis. Offline fixtures are consolidated screener pages, so standalone cards (IDFCFIRSTB, BAJFINANCE fixtures) are reported "skipped: basis mismatch". Live mode fetches the matching basis page — cost if wrong: offline coverage is TATASTEEL only.
- Ruling R6: the `.txt` fixtures were extracted with PyMuPDF during the spike and are used only as text inputs; runtime uses pypdf (BSD). The text-level tests don't depend on the extractor; `hello.pdf` covers the pypdf path — cost if wrong: none.

## Progress
Task 1: dispatched (sonnet), base 6ba29cc
Task 1: implementer DONE 35c48e4 (207 passed); review dispatched (sonnet)
Task 1: review (sonnet) Approved, 0 Critical/0 Important. ⚠️ resolved by controller: no other consumers of route "bio"/finn_model_bio outside config + router tests (grep); full suite 207 passed.
Task 1: minor (deferred): unused tmp_path arg in test_chain_for_dedupes_primary_and_fallback (test_llm_router.py:387)
Task 1: minor (deferred): 5xx-fallback test doesn't pin no_sleep == [1]
Task 1: minor (deferred): a primary's Retry-After still sleeps up to 60 s before failover (router.py:243) — fine for batch refresh; revisit if live paths use the router
Task 1: minor (deferred): no direct assertion that a fallback answer is cached under the fallback model's key
Task 1: complete (35c48e4)
Task 2: dispatched (sonnet), base 35c48e4
Task 2: implementer DONE_WITH_CONCERNS 13e4b8d (223 passed; concerns: _get check-callback, fetch_bytes non-streaming) — observations, to review
Task 2: review (sonnet) Approved, 0 Critical/0 Important. ⚠️ resolved by controller: tests/test_xbrl.py + tests/test_nse.py pass (fixture values and announcement error text verified by the run).
Task 2: minor (deferred): fetch_bytes content-length pre-check runs after the full download (nse.py:141-148) — stream with a running byte count
Task 2: minor (deferred): _get_json passes its result via a side effect in check + type: ignore (nse.py:88-122,136)
Task 2: minor (deferred): _reason splits the exception text on " failed: " (nse.py:151) — give NSEUnavailable a .reason
Task 2: minor (deferred): INTEGRATED_TYPE duplicated in xbrl.py:187 and nse.py:30
Task 2: minor (deferred): float() accepts nan/inf in XBRL facts (xbrl.py:324) — add an isfinite guard (would poison card math)
Task 2: minor (deferred): ET.fromstring has no entity-expansion guard (xbrl.py:296); source is NSE and size is capped by fetch_bytes
Task 2: minor (deferred): test gaps — parse_xbrl audited True/None; "Unaudited" spelling; body-only oversize; fetch_bytes retry on non-200
Task 2: complete (13e4b8d)
Task 3: dispatched (sonnet), base 13e4b8d
- Ruling R7 (T3): metrics_for treats non-finite facts (nan/inf) as None — the Task 2 parser does not filter them (deferred minor), and one bad fact must not poison a % — cost if wrong: none
Task 3: implementer DONE 6dddb05 (234 passed)
Task 3: review (sonnet) Approved, 0 Critical/0 Important. ⚠️ resolved by controller: tests/test_results.py passes (fixture values), ruff check + format clean.
Task 3: minor (deferred, USER-VISIBLE): negative exceptional/associates amounts render "₹-345.48 cr" (results.py:270,276) — say "exceptional loss/gain of ₹345.48 cr"
Task 3: minor (deferred): lambda assigned to _EBITDA (results.py:86); _usable lacks a return annotation (:182); assert used for narrowing (:62)
Task 3: minor (deferred): test gaps — prior revenue 0 → margin None; bank/NBFC exceptional note; bps tolerance abs=1
Task 3: complete (6dddb05)
Task 4: dispatched (sonnet), base 6dddb05
Task 4: implementer DONE d40e977 (243 passed; concern: list basis overrides the parsed XBRL basis)
Task 4: review (sonnet) Needs fixes — 3 Important: (1) list basis overrides the document basis (the test asserted the mislabel); (2) the standalone fallback test asserts nothing real; (3) rows are keyed on the XML symbol, not the requested symbol.
- Ruling R8 (T4): trust the XBRL document's basis; a list/document basis mismatch skips that target and is recorded in failed ("basis mismatch"). Store rows under the requested symbol (model_copy). Standalone tests use synthetic standalone XML (NatureOfReport edited) — cost if wrong: one more skipped target per mismatch, surfaced in errors.
Task 4: minor (deferred): only XbrlError is caught per target; an NSEUnavailable on one target aborts the symbol's remaining targets (results.py:240)
Task 4: minor (deferred): a skipped URL is counted without checking that the stored row's basis/period match the target (results.py:236)
Task 4: minor (deferred): db.py imports finn.ingest.xbrl (layering inversion, no cycle)
Task 4: minor (deferred): no direct tests for the get_financials round trip / IST offset preserved / audited tri-state / re-filing replacement; _sleep never asserted
Task 4: fix round 1 dispatched (resume implementer), fix base d40e977
Task 4: fix round 1/5 (3 addressed, 0 open; commits d40e977..a99dacd)
Task 4: complete (a99dacd)
Task 5: dispatched (sonnet), base a99dacd
Task 5: implementer DONE 2edd7e2 (252 passed)
Task 5: review (sonnet) Approved, 0 Critical/0 Important. ⚠️ resolved: timezone awareness + the sole build_digest caller were checked by the reviewer; controller ran test_digest_results.py + test_api.py (pass).
Task 5: minor (deferred): no test that a routine-list story gets results; no test pinning the once-per-symbol card_for cache; results_card route lacks a docstring (main.py:55)
Task 5: complete (2edd7e2)
Task 6: dispatched (sonnet), base 2edd7e2
Task 6: implementer DONE bd48340 (260 passed)
Task 6: review (sonnet) Approved, 0 Critical/0 Important. ⚠️ resolved: test_pdftext.py passes (controller run). ⚠️ oversize PDF → NSEUnavailable is not cached, so it would be re-downloaded every refresh → Ruling R9.
- Ruling R9 (T7): add `class PayloadTooLarge(NSEUnavailable)` in nse.py, raised by fetch_bytes for oversize; get_doc_text catches PayloadTooLarge and caches "" (permanent: never re-downloaded); other NSEUnavailable still propagates uncached (transient, retried). The subclass keeps existing callers' behaviour — cost if wrong: a large filing is skipped until the cache row is deleted.
Task 6: minor (deferred): pypdf logger level is changed process-globally inside extract_text (thread-unsafe; refresh is single-threaded) (pdftext.py:99-109)
Task 6: minor (deferred): the relevant_window final cut can drop late hits when early windows are large; no per-hit trimming (pdftext.py:139)
Task 6: minor (deferred): no test that max_bytes is forwarded to fetch_bytes; a cached "" is permanent even for a transiently unparseable PDF (as specified)
Task 6: complete (bd48340)
Task 7: dispatched (sonnet), base bd48340
- Ruling R10 (T7/T8): a shared FakeRouter in tests/fakes.py (reply = dict | callable | Exception; records calls; last_model set) — one LLM double for both enrichment tasks — cost if wrong: a move
Task 7: implementer DONE 114763f (282 passed)
Task 7: review (sonnet) Needs fixes — 4 Important: (1) dead honorific lookbehind lets a fabricated profile return "Mr."; (2) an unhashable `change` crashes the stage, and there is no per-filing catch-all; (3) role/effective ungrounded; (4) the filter test asserts nothing.
- Ruling R11 (T7, amends the plan): name_in_text needs ≥ 2 tokens after honorific strip plus a word-boundary match ("Ann" vs "Annexure"); a kept profile sentence needs ≥ 4 words; role/effective kept only if they appear in the text; per-filing catch-all in enrich_people — cost if wrong: a single-name person (rare in LODR filings) is dropped.
Task 7: minor (deferred): grounding proves a sentence is in the filing, not that it belongs to that person (multi-profile PDFs) — inherent to the plan
Task 7: minor (deferred): non-contiguous kept sentences read as adjacent (grounding.py:239-255)
Task 7: minor (deferred, DEMO-RISK): attach_people model_validates stored rows at request time; one corrupt row breaks the digest (people.py:477) — wrap and skip
Task 7: minor (deferred): first-appearance dedupe can discard a later record that carries a profile (people.py:478)
Task 7: minor (deferred): numbers_grounded treats "5000.00" ≠ "5000"; "Q2FY26" yields tokens 2/26 (safe side)
Task 7: fix round 1 dispatched (resume implementer), fix base 114763f
Task 7: fix round 1/5 (5 addressed, 0 open; commits 114763f..4028ab0)
Task 7: minor (deferred): effective is kept only if verbatim in the text, so it may often be None when the LLM reformats dates
Task 7: complete (4028ab0)
Task 8: dispatched (sonnet), base 4028ab0
- Ruling R12 (T8): a transient LLMError with an NSE summary present saves nothing (retry next refresh); a validation rejection saves the NSE-summary fallback (no infinite retry); attach_briefs skips corrupt rows; the same type-check and catch-all robustness as T7 — cost if wrong: a brief appears one refresh later
Task 8: implementer DONE a960ebb (306 passed; make_brief has a category kwarg; LLMError propagates per R12)
Task 8: review (sonnet) Needs fixes — 2 Important: fact values with no digits pass on tiny substrings (brief.py:171); quote with no min length/boundary (brief.py:196). ⚠️ resolved: headline is always chosen from members (cluster.py:21,42); malformed JSON raises LLMError → retried (consistent with R12).
- Ruling R13 (T8): a shared grounding.phrase_in_text(phrase, text, min_words) with word boundaries; facts without digits need ≥ 3 chars + phrase_in_text; quotes need ≥ 4 words + phrase_in_text — cost if wrong: fewer facts/quotes shown
Task 8: minor (deferred): a fact value mixing grounded digits with ungrounded words passes ("Zeta Corp, 100%"); labels unchecked; number words not caught
Task 8: minor (deferred): one-liner checked for numbers only — can name an uninvented counterparty (spec limit; record in EVALS/writeup)
Task 8: minor (deferred): below-MIN_SCORE filings are rescored every refresh (cheap); no MIN_SCORE boundary test; no tests for NSEUnavailable→failed or LLMError + no summary
Task 8: fix round 1 dispatched (resume implementer), fix base a960ebb
Task 8: fix round 1/5 (2 addressed, 0 open; commits a960ebb..42ae2c3). The fix report carried only a summary line, so the controller ran test_brief.py + test_grounding.py and the full suite itself.
Task 8: minor (deferred): a 3-char value like "Ltd" passes when present in the source (grounded but junk)
Task 8: complete (42ae2c3)
Task 9: dispatched (sonnet), base 42ae2c3
Task 9: implementer DONE 1d456aa (321 passed; offline eval TATASTEEL 4/4; autouse stub for the new stages in test_refresh)
Task 9: review (sonnet) Needs fixes — 3 Important: (1) enrichment stages run before classify_pending; (2) live parse_quarters is fed the full multi-table page (P&L rows would overwrite quarterly values); (3) the bank/nbfc PAIRS mapping is untested.
- Ruling R14 (T9): the stage order is filings → prices → classify → financials → people → briefs; parse_quarters isolates section#quarters (falling back to whole input) and its first table; a test checks the PAIRS keys exist in build_card metrics per format; stale DESIGN.md hosting/Gemini text is fixed as part of this round (docs are a deliverable) — cost if wrong: none
Task 9: minor (deferred): diff % lacks a sign convention/% sign; local imports in _fixture_conn; parse_quarters doesn't handle nested td / duplicate labels (last wins)
Task 9: fix round 1 dispatched (resume implementer), fix base 1d456aa
Task 9: fix round 1/5 (4 addressed, 0 open; commits 1d456aa..6c3de47)
Task 9: complete (6c3de47)
All tasks complete. Final review: dispatching (opus), range dbfa7f7..6c3de47
Live refresh (controller, scratch seed, pre-T9-fix code): financials 52 fetched; 17/18 have Sep 2026 (AMBER not yet posted); people 24 done/5 empty/1 failed; briefs 39 done/2 empty; 69 LLM calls, $0.06 list price.
Live finding L1: revised integrated filings have broadcast_Date null + revised_Date set → parse_filing_list skips them as malformed (14 rows) and falls back to the erroneous originals (CGPOWER/IDFCFIRSTB Sep-2025: OneD spans 6 months → YoY lost); elsewhere it may silently use uncorrected numbers.
Live finding L2: Groq 8K TPM → 429 on back-to-back enrich calls; 1 retry for a non-last model → failover to Gemini Flash-Lite → invalid JSON escape → filing failed.
Final review dispatched (opus) with L1-L3.
Final review (opus): With fixes — C1 (revised filings dropped → erroneous originals; keep the original broadcast as filed_at), I1 (429 treated as an outage), I2 (request-time raise on a corrupt people/financials row), I3 (DESIGN stale ×5); FIX-BEFORE-MERGE minors: T1 sleep pin, M1 note wording + per-format lenders note, M2 format check in _usable, M3 fact words, M5 role phrase_in_text, M6 _router any key, M8 API people/brief test. Plan defects PD1-PD6 recorded.
- Ruling R15 (final): one fix wave per final-fix-brief.md; STAY-DEFERRED: M4 unit-aware numbers, M5 name-near-change proximity, M7 bad-URL cache/exit-code split (→ Plan 5), and all other STAY-DEFERRED triage lines; EVALS gets a "Limits of the grounding guard" note (PD3) — cost if wrong: attribution/unit errors remain possible and are disclosed.
Final fix wave: dispatched (opus), fix base 6c3de47
Final fix wave: DONE_WITH_CONCERNS (368 passed; commits 6c3de47..a2e6447; 5 deviations, all accepted by the re-review).
Final fix re-review (sonnet): all of C1/I1/I2/I3/M1/M2/M3/M5/M6/M8/Limits ADDRESSED; no new Critical/Important breakage.
Parked: /results/{symbol} still 500s on a corrupt financials row (api/main.py:215) — Ruling: carry into the next plan's first task as a one-line fix (reuse digest._card_or_none); low risk because writes are pydantic-validated.
Parked: a refresh exits 1 on "not on file" targets (new listings) — M7, Plan 5 scheduler.
Live refresh #2 (fixed code): C1 healed live (CGPOWER/IDFCFIRSTB regain Sep-2025). Timed out twice (30 + 60 min): Groq TPD 200K exhausted (Used 198,702; retry-after 781 s), and the I1 pacing waited 3 × 60 s per call before failing over. Enrichments so far: people 30, briefs 36 (models: groq 37, gemini 23).
Live eval_results: 68/70 pairs match (97.1%); both misses (VOLTAS, TRENT EBITDA) are screener netting a negative JV share into expenses (ours + share = screener). EVALS.md §2 live result written.
- Ruling R16: post-review addendum Task 10 — a 429 with Retry-After > 60 s is quota exhaustion → no sleep, provider skipped until reset, immediate failover; pacing 429s unchanged — found live after the single final fix wave, so handled as its own reviewed task rather than a second fix wave — cost if wrong: a provider is skipped for its stated reset window.
Task 10: dispatched (sonnet), base a2e6447
Task 10: implementer DONE 3a9b6d8 (373 passed; clamp test case 120→60 since >60 is now quota)
Task 10: review (sonnet) Approved, 0 Critical/0 Important.
Task 10: minor (CARRY TO PLAN 3 TASK 0): _exhausted_until is keyed by provider, but quotas are per model (Groq TPD "for model …", Gemini per model), so a Gemini-primary quota would skip its Gemini fallback — key by (provider, model)
Task 10: minor (deferred): no test of the _retry_delay upper clamp now (add a direct _retry_delay("120",0)==60); duplicated Retry-After parsing; docstring wrap
Task 10: complete (3a9b6d8)
Seed installed (01e31ed): 54 financials, 30 people, 41 briefs; live eval 68/70; 373 passed.
Carry to Plan 3 Task 0: (a) /results/{symbol} guard via _card_or_none; (b) key quota exhaustion by (provider, model); (c) results attach window — a same-quarter story filed >4 days after the XBRL (BAJFINANCE half-yearly report, Nov 7 vs Oct 19) gets no card; allow up to ~45 days after the card's filed_at while it is still the latest period.
Plan 2: COMPLETE.
