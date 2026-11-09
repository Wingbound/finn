# SDD ledger — plan: docs/superpowers/plans/2026-11-09-plan3-pull-research.md

Spec: docs/DESIGN.md. Branch feat/pull-research from main 49477a8. Plan + fixtures commit: see git log.

## Pre-flight scan

| pair / task | produces → consumes | finding |
|---|---|---|
| T1→T2 | parse_table dicts → trajectory/balance_sheet_health | consistent |
| T1→T3 | parse_documents → collect_sources | consistent |
| T3→T4 | Source(pages) → extract_promises; cite.locate(Source) | consistent |
| T4→T5 | Promise, locate → build_ledger | consistent |
| T5/T2→T6 | Ledger, Trajectory, Health → bull_bear | consistent |
| T1-T6→T7 | all → build_dossier | consistent |
| T7↔T8 | T8 adds Dossier.guard + populates it in build_dossier (touches the T7 file) | sequential; consistent |
| T0 self | the attach-window change breaks an existing far-apart test (+43 d) | plan already moves that test to +69 d |
| T5 self | relevant_window takes plain text; the judge needs page tags | apply it to tagged_text output (implementer's choice) |
| each task self | tests vs interfaces | consistent |

## Rulings
- Ruling P3-R1: LLM budget per dossier = guidance ≤ 4 + ledger ≤ 3 (T2..T4 sources; T1 promises are pending with no call) + synthesis 2 = 9 ≤ 12 — cost if wrong: none.

## Progress
Task 0: dispatched (sonnet), base a21d766
Task 0: implementer DONE 91e5636 (377 passed)
Task 0: review (sonnet) Approved, 0 Critical/0 Important. ⚠️ resolved: controller ran the full suite (pass).
Task 0: minor (deferred): attach_results docstring line ~110 chars; no exact +45 d / −4 d boundary tests
Task 0: complete (91e5636)
Task 1: dispatched (sonnet), base 91e5636
Task 1: implementer DONE cdd81fb (386 passed; TDD order inverted — RED via stash; parse_table {} on a full page missing the section)
Task 1: review (sonnet) Approved, 0 Critical/0 Important. ⚠️ resolved: controller ran live search('persistent'/'hdfc bank'/nonsense) + fetch_company('DIXON') successfully with the v/fts params.
Task 1: minor (deferred): full-page vs fragment heuristic is `"<section" not in html` (screener.py:69) — an interstitial page with a table could false-positive
Task 1: minor (deferred): transcript/PPT matched by exact link text; TDD order inverted (process)
Task 1: complete (cdd81fb)
Task 2: dispatched (sonnet), base cdd81fb
Task 2: implementer DONE 0477dd2 (397 passed; lender CFO/PAT flag kept)
Task 2: review (sonnet) Approved, with 1 Important (lender CFO/PAT flag misleading). Values verified against the fixture by the reviewer.
- Ruling P3-R2 (T2): lenders get cfo_to_pat_3y None and no CFO/PAT flag; _cagr takes n from the year labels; Σ PAT ≤ 0 gives CFO/PAT None and no flag — cost if wrong: lenders show fewer flags.
Task 2: minor (deferred): untyped _sum3 getter; FCF flag renders "₹-30 cr"
Task 2: fix round 1 dispatched (resume implementer), fix base 0477dd2
Task 2: fix round 1/5 (3 addressed, 0 open; commits 0477dd2..1a70707)
Task 2: complete (1a70707)
Task 3: dispatched (sonnet), base 1a70707
Task 3: implementer DONE 2857377 (412 passed)
Task 3: review (sonnet) Approved, with 2 Important: unparseable date/KeyError and non-DocError exceptions (InvalidURL, sqlite3) escape collect_sources.
- Ruling P3-R3 (T3): per-source catch-all in collect_sources with a note; call_quarter still raises (documented) — cost if wrong: none.
Task 3: minor (deferred): DocClients unclosed in tests; newest-first ordering inherited from parse_documents (document the contract); a cached AR keeps its first max_pages cut
Task 3: fix round 1 dispatched (resume implementer), fix base 2857377
Task 3: fix round 1/5 (2 addressed, 0 open; commits 2857377..0d07309)
Task 3: minor (deferred): progress() inside the broad except (a callback bug becomes a skip note)
Task 3: complete (0d07309)
- Ruling P3-R4 (T4): locate also tries adjacent page pairs (cite the first page) so page-straddling quotes survive; tagged_text max_chars = 90_000 (whole transcripts fit; the Q&A holds much of the guidance) — cost if wrong: ~22k tokens per extraction call on Flash-Lite (free).
Task 4: dispatched (sonnet), base 0d07309
Task 4: implementer DONE c81f9ea (429 passed; TDD order inverted again)
Task 4: review (sonnet) Approved, 0 Critical/0 Important; the citation guard can't cite absent text.
- Ruling P3-R5 (T4, minors promoted — the hero feature): (1) locate rejects a match whose same-sentence prefix has a negation token (fragment meaning inversion); (2) grounding.numbers_grounded ignores period-label digits (FY27, Q2, H1, 9M, 2Q) on both sides — a shared module, so Plan 2 briefs tighten too; (3) kind/unit normalised to the targets kept — cost if wrong: some real fragments dropped (lower recall).
Task 4: minor (deferred): a range truncated mid-fragment ("grow 15" of "15-18%"); :g formatting for ≥1e6 targets (safe failure); "22.50" vs 22.5 demotes (safe)
Task 4: fix round 1 dispatched (resume implementer), fix base c81f9ea
Task 4: fix round 1/5 (3 addressed, 0 open; commits c81f9ea..8f5e5e4)
Task 4: minor (deferred): "9M" (nine million) is now treated as a period label; glued "Q4FY27" not stripped (safe)
Task 4: complete (8f5e5e4)
Task 5: dispatched (sonnet), base 8f5e5e4
Task 5: implementer DONE 63c9c8f (477 passed; resumed after the rate-limit stop)
Task 5: review (sonnet) Needs fixes — 2 Important: (1) "H2 FY27"/"exit FY27"/"FY27-28" are graded against the full FY; (2) lo ≤ 0 inverts the partly band.
- Ruling P3-R6 (T5): parse_horizon resolves only exact labels/phrases (optional in/for/during prefix), else judged; lo ≤ 0 → judged; absent row labels → judged (not a false "not published"); the "later" key = source.quarter (fallback made_in); numeric id sort — cost if wrong: more rows judged by the LLM (evidence-gated).
Task 5: minor (deferred): target_high ignored (a range exceeded grades kept without saying so); actual rounded to 2 dp before grading; "fy" alone = this year
Task 5: fix round 1 dispatched (resume implementer), fix base 63c9c8f
Task 5: fix round 1/5 (5 addressed, 0 open; commits 63c9c8f..68c7d93)
Task 5: complete (68c7d93)
- Ruling P3-R7 (T6): FACTS block built by code from trajectory/health/ledger (CAGR, margin bps, D/E, CFO/PAT, FCF, ledger counts/credibility); point numbers must ground in quote + FACTS; >30-word points dropped; snapshot input = AR first 10 pages (if any) + T1 first 4 pages; bull/bear input = FACTS + ledger row summaries + tagged_text(T1, 30000) + AR first 10 pages — cost if wrong: fewer points
Task 6: dispatched (sonnet), base 68c7d93
Task 6: implementer DONE 50ae9f0 (498 passed)
Task 6: review (sonnet) Approved, 0 Critical/0 Important.
Task 6: minor (deferred): no dedupe of points citing the same quote; source_id may name a source not shown to the model (locate still verifies); FACTS numbers can be misattributed to any quote (inherent) — the UI must not present FACTS numbers as quoted (Plan 4 note)
Task 6: complete (50ae9f0)
- Ruling P3-R8 (T7): the SSE build thread opens its own SQLite connection (db.connect(settings.db_path) + init_db) — sqlite3 connections are not shareable across threads; the request's Conn dependency stays in the request thread — cost if wrong: none
Task 7: dispatched (sonnet), base 50ae9f0
Task 7: implementer DONE 45037fb (512 passed)
Task 7: review (sonnet) Approved, 0 Critical/0 Important.
Task 7: minor (deferred): the worker's conn.close() runs before q.put(_DONE) (a close() raise would hang the stream); no in-flight build dedupe; soft deadline overrun on slow I/O; no cost-delta test with a stats() stub
Task 7: complete (45037fb)
Live build #1 (controller, scratch DB): PERSISTENT 237 s, 9 calls, $0.039; trajectory/health/snapshot/bear good; ALL 14 ledger rows pending (6000-char evidence windows miss follow-ups); bull empty (the model cited source_id "FACTS"); current-fact statements extracted as promises; the reason chain wasted time on gemini-3.8-flash.
- Ruling P3-R9: addendum Task 7b — (A) judge sees full later transcripts; (B) reason/extract_transcript chains = 3.5-flash-lite → 3.1-flash-lite; (C) forward-looking-only extraction; (D) FACTS lines citable in bull/bear (page 0, exact line); (E) honest progress text — live evidence after the task reviews, so handled as a reviewed addendum task — cost if wrong: ~3× judge tokens (~$0.03/dossier list).
Task 7b: dispatched (sonnet), base 45037fb
Task 7b: implementer DONE 3761a74 (519 passed; the safety-block router test now mocks the 3.1 fallback URL)
Task 7b: review (sonnet) Approved; 1 Important: no total cap on the judge prompt (~70k tokens worst case, Gemini-only fallbacks). The router test edit was judged stronger, not weaker.
Task 7b: minor (deferred): FACTS substring matches on raw chars (mid-word); a vacuous assertion in test_system_prompt_forward_looking_only
Task 7b: complete (3761a74)
Live build #2: PERSISTENT 30 s, 9 calls, $0.064; 18 rows: 5 kept (real later evidence, e.g. Nagarro 94.04% vs a 50%+1 threshold), 13 pending; credibility 100% inflated — a "16-17% margin aspiration" was judged kept on mere reiteration; pending rows carried unrelated evidence.
- Ruling P3-R10: addendum Task 7c (resume the 7b implementer) — sharpen the status definitions ("restating is NOT delivery"), pending rows drop evidence, total judge evidence budget 200k chars split across later sources — cost if wrong: fewer kept rows (more honest).
Task 7c: dispatched (resume), base 3761a74
Task 7c: implementer DONE fc8e9da (525 passed)
Task 7c: review (sonnet) Approved, 0 new problems.
Task 7c: complete (fc8e9da)
Live build #3: PERSISTENT 34 s, $0.037; 4 kept (outcome evidence), 1 dropped, 13 pending; the margin aspiration is now correctly pending; 0 pending rows with evidence.
- Ruling P3-R11 (T8): guard counters — extract_promises gains an optional guard dict (promises_proposed/promises_kept) like synthesis; build_dossier passes one guard dict to guidance + synthesis and stores it as Dossier.guard; eval re-verifies FACTS citations against a facts_block recomputed from the stored trajectory/health/ledger — cost if wrong: none
Task 8: dispatched (sonnet), base fc8e9da
Task 8: implementer DONE 9f997b5 (530 passed)
Task 8: review (sonnet) Approved, 0 Critical/0 Important; every DESIGN.md claim checked against the code.
Task 8: minor (FIX IN FINAL WAVE — docs are a deliverable): "at most 12 LLM calls" reads as an enforced cap (it is a budget; the structural worst case is ~9); the DESIGN grading bullet omits the numeric thresholds and the lo ≤ 0 → judged rule; the eval omits the FACTS count from the table
Task 8: complete (9f997b5)
All Plan 3 tasks complete. Demo live builds running (PERSISTENT DIXON POLYCAB INDIGO).
Demo live builds (scratch): PERSISTENT/DIXON/POLYCAB/INDIGO — citations 122/122 (100%); ledger 14 kept/0 partly/2 missed/65 pending/2 dropped; computed 3/83; promise drop 18%, point drop 31%; $0.19 list total; 36-58 s each. Good misses: POLYCAB EHV capacity slipped to FY2028; INDIGO. Errors: segment past-fact extracted and computed vs company margin; FY30 targets judged kept on "tracking"; period mismatch (Q4 guidance vs Q1 actual); a conditional "if…" extracted.
- Ruling P3-R12: addendum Task 7d (resume the 7b implementer) — a future-cue filter on promises; no computed grade for segment-level quotes; judged kept/partly → pending for future or long-horizon targets; a same-metric/period rule in the judge prompt — cost if wrong: fewer rows, fewer kept (more honest).
Plan 4 note: the UI should split "open promises (latest call)" from the "track record (earlier calls)", since latest-call promises are always pending.
Task 7d: dispatched (resume), base 9f997b5
Task 7d: implementer DONE 4f5e3e7 (537 passed)
Task 7d: review (sonnet) Approved.
Task 7d: minor (FIX IN FINAL WAVE): the prefix cue "plan" matches "plant"/"planet" and "will" matches "willing" (guidance.py:47) — manufacturers talk about plants constantly; bare-year cue 2028-2032 is conservative-only (downgrades kept)
Task 7d: complete (4f5e3e7)
Final review: dispatching (opus), range 49477a8..4f5e3e7
Final review (opus): With fixes — C1 the computed path trusts the LLM's period/metric (same-quarter, Q4 "this year", EBIT/QoQ/USD/margin-change vs EBITDA/YoY, lender NIM → negative financing margin); C2 negative net worth → "Virtually debt-free"; I1 judge rationale ungrounded; I2 silent LLM failures + degraded dossiers overwrite good ones; I3 300 s overrun paths; I4 conditionals/past facts pass extraction; I5 judged-path period handling weak; I6 FACTS numbers on page chips; I7 credibility on tiny samples; I8 SSE ordering/excerpts; I9 docs contradictions. PD: generalisation run (bank, NBFC, negative equity) required.
- Ruling P3-R13 (final): one fix wave per final-fix-brief.md (C1-C2, I1-I8, selected minors, docs); everything else STAY-DEFERRED per the reviewer triage — cost if wrong: fewer computed rows (more judged), stricter extraction.
Final fix wave: dispatched (opus), fix base 4f5e3e7
Final fix wave: DONE (727 passed; 10 commits 4f5e3e7..7105070; deviations accepted pending re-review)
Final fix re-review (sonnet): every item ADDRESSED (probes confirm C1/C2/I4/I5 give safe results); all deviations accepted; no new breakage.
Parked: SSE timeout ends the stream but the worker may still save (acceptable); JUDGE_EVIDENCE_CHARS makes the oldest call's promises un-droppable (acceptable: the T3 group can still be dropped); PROJECT_BRIEF.md:194 "HF Spaces (Docker)" stale → Plan 5 docs pass.
Live rebuild (fixed code, 7 tickers incl. HDFCBANK/BAJFINANCE/IDEA): citations 139/139; 14 FACTS citations; $0.39 list; 18-48 s each; generalisation built cleanly for a bank, an NBFC and negative equity. BUT the ledger over-corrected: 6 kept / 0 missed / 86 pending / 1 dropped, computed 0/93; promise drop 42% (DIXON 67%, HDFCBANK 71%); POLYCAB's real EHV miss lost — the cause is the whole-word cue fix rejecting "is expected/planned/scheduled to" (passive future).
- Ruling P3-R14: addendum Task 7e — accept passive/predicative future forms (is/are/be/remain + expected/planned/scheduled/…/to|for); past forms stay rejected — cost if wrong: some past-tense passives slip (rare).
Task 7e: dispatched (sonnet), base 7105070
Task 7e: implementer DONE e4705e6 (736 passed)
Task 7e: review (sonnet) Needs fixes — pattern 2 (no auxiliary) lets past passives through ("was planned to be commissioned…").
Task 7e: fix round 1 dispatched (resume): remove pattern 2 + past-tense tests, fix base e4705e6
Task 7e: fix round 1 done 6b4cd94 (740 passed)
Task 7e: fix round 1/5 re-review ADDRESSED; complete (6b4cd94)
Judge A/B (live, POLYCAB/DIXON/INDIGO): Flash-Lite judge → 0 missed (EHV slip judged pending); gemini-3.5-flash judge → 3 correct misses + 1 correct kept (hand-audited), 4 INDIGO "dropped" (plausible, absence unverifiable); 72-80 s each. 3.8 Flash still 503.
- Ruling P3-R15: addendum Task 7f — reason → gemini-3.5-flash, falling back to 3.5-flash-lite, then 3.1-flash-lite; 3.5 Flash is unpriced on the published list (UNPRICED_MODELS, no invented price) — cost if wrong: unpriced calls understate the cost ledger (disclosed).
Plan 4 note: label "dropped" as "not mentioned again" (an absence, unverifiable).
Task 7f: dispatched (resume 7e implementer), base 6b4cd94
Task 7f: implementer DONE 7600d70 (741 passed)
Task 7f: review (controller, inline; the 26-line config/cost diff was read in full, and the sonnet reviewer seat was lost to the 5-hour limit) Approved: the chain matches P3-R15; UNPRICED_MODELS suppresses only the warning; the tests pin the chain and the zero-cost no-warn path.
- Ruling P3-R16: the controller reviews tiny mechanical diffs (≤30 lines, config/docs) inline — cost if wrong: one less independent pair of eyes on a config change that the tests already pin.
Task 7f: complete (7600d70)
Seed: the scratch final_seed.sqlite was lost (temp dir cleared); rebuilding the 7 dossiers into backend/data/build_seed.sqlite (git-ignored).
Rebuild (fixed code, live, 2026-11-09 21:xx): 7 dossiers, citations 145/145, 17 FACTS; ledger 9 kept/0 partly/2 missed/81 pending/2 dropped; computed 0/94; promise drop 36%, point drop 29%; $0.39 list (3.5 Flash unpriced); 81-99 s each. Run-to-run variance: POLYCAB's original EHV promise not extracted this time (only the FY2028 restatement, pending); DIXON Noida judged kept on a restatement.
Hand audit (11 resolved): correct 5 (INDIGO Q1 capacity kept; PERSISTENT ETR kept; PERSISTENT streak kept; PERSISTENT AGM→EGM missed; HDFCBANK interim chair kept, trivial); debatable 3 (HDFCBANK MD announcement, rationale names a person not in the quote; INDIGO end-June 90-95% kept, partly is fairer; INDIGO Q2 flattish kept on weak evidence); wrong 3 (DIXON restated target kept; IDEA 42 < 50-60 kept; INDIGO Q4 FY26 graded on June-quarter evidence). Dropped 2: unverifiable absences.
- Ruling P3-R17: addendum Task 7g — three deterministic verdict guards (other period, restated target, below target), downgrade-only to pending, with counts in guard — cost if wrong: some correct verdicts become pending (more honest than wrong ones).
Task 7g: dispatched (sonnet), base 7600d70
Task 7g: implementer DONE 83d14c3 (753 passed; two pre-existing tests adjusted)
Task 7g: review (sonnet) Spec ✅, Approved with fixes: I1 fused period labels (H1FY26) parsed as numbers; I2 present-tense deliveries with a future cue downgraded; minors: "had planned" counted as delivery, the "missed" workaround in a test, rationale wording. Mixed-quarter evidence stays per brief.
Task 7g: fix round 1 dispatched (resume), fix base 83d14c3
Task 7g: fix round 1 done 747104b (757 passed); scoped re-review (controller, inline, 15-line code diff per P3-R16): every finding addressed
Task 7g: complete (747104b)
