# SDD ledger — plan: docs/superpowers/plans/2026-11-10-plan6-one-loop.md
Spec: docs/DESIGN.md §1 (results card vs promise), §8. Executor: inline on feat/one-loop from main b1b5d61. User asked: "improve the work".
- Ruling P6-R1: notes, not grades — the stored numeric guidance is too noisy for auto-grading (AUM and PRASK tagged as revenue_growth, mostly FY or long-term horizons), so one quarter never grades a promise; a pace note only fires under strict gates — cost if wrong: fewer pace notes (by design).
Pre-flight: T1 (Story.promises, PromiseNote) → T2 (types.ts, PromisePanel); T2 (latest_results) → dossier view. Consistent.
- Task 1: Ruling: a target label is shown only with a unit and numbers grounded in the quote — the live preview showed "180–600" (two merged figures) and "$650 mn" beside a quote saying $125 million — cost if wrong: fewer target labels (the quote stays).
Task 1: complete (commits b1b5d61..1491df6, tests: bash -c 'cd backend && uv run pytest -q' → 822 passed in 24.96s)
- Task 2: Ruling: e2e and unit tests that pinned "7 things matter", "7 Nov, 16:58" and story ids now read from the fixtures — the daily refresh changes the snapshot, so fixture-pinned literals rot — cost if wrong: none.
Task 2: complete (commits 1491df6..0db55c2, tests: bash -c 'cd backend && uv run pytest -q && cd ../frontend && npx vitest run && npx playwright test' →   35 passed (9.9s))
- Task 3: Ruling: two cheap deferred minors fixed while the builds ran: Plan 5 M1 (atomic seed copy, test_deploy "interrupted seed copy" RED→GREEN) and Plan 4 M5 (one live region on progress lines only, research.test RED→GREEN) — the user asked to improve the work — cost if wrong: none.
Task 3: complete (commits 0db55c2..ed5235e, tests: bash -c 'uv run pytest -q && cd ../frontend && npx vitest run && npx playwright test' →   35 passed (31.9s))
- Task 3: Ruling: the second audit (16 new dossiers) found 5 more mechanical verdict errors → two new downgrade-only checks (other measure, meets target) plus restated-cue fixes, applied by a cached rebuild of all 23 dossiers — cost if wrong: some correct verdicts become pending (none of the audited-correct ones did).
- Task 3: Ruling: TRENT (no earnings calls) gets an explicit ledger note — cost if wrong: none.
- Task 3: Ruling: target labels also need their unit in the quote; "at least" only when the words sit beside the number; Indian grouping; repeated guidance deduped — found by reading real notes — cost if wrong: fewer target labels.
Final review (opus): ready with fixes. No Critical; I1-I7; M1-M9. Focus items 1-5 hold on the real seed.
- Final: Ruling: M2, M3, M4, M5, M7 and M8 re-graded to Important — plan rules (M2, M5), user-visible copy (M4, M8), a lost valid pace note (M3), wrong numbers in EVALS (M7) — cost if wrong: none.
Final: fixed I1/I2 — test_link "no_pace_for_neighbouring_measures" (16 cases), "point_targets_are_not_floors" RED→GREEN
Final: fixed I3 — test_link "a_q4_calls_this_year_is_not_this_card" RED→GREEN
Final: fixed I4 — test_link "horizons_read_correctly_on_a_later_card" (7 cases), loop.test "the note's period" RED→GREEN
Final: fixed I5 — test_link "a_cut_is_not_a_target", "only_results_lines_are_called_targets" RED→GREEN
Final: fixed I6/I7 — test_research_ledger "delivered_sentences_stay_kept" (6), "adverb_after_the_modal" (4) RED→GREEN; found during re-application: LODHA "annual" kept mid-year → test "annual_target_judged_mid_year_is_not_yet_due" RED→GREEN
Final: fixed M2/M3/M4/M5/M8 — tests "far_targets_rank_after_near_ones", "dedupe_keeps_the_copy_with_a_pace_note", "a_quarter_target_says_so" + loop.test scope, "a_corrupt_dossier_gives_no_notes", loop.test "doesn't point at promises" RED→GREEN
Final: fixed M7 — EVALS numbers (332 rows, 18 firings, five guards); loop screenshot retaken
Suite after the pass: pytest 882/882, vitest 200/200, Playwright 35/35; 23 dossiers re-applied from cache; ledger 21 kept / 2 missed / 306 pending / 3 dropped (the audited set: 14 correct, 9 debatable, 0 wrong).
Final: minor (deferred): M1 "meets"/"below" rationales use a 2% tolerance (23.6% "meets" at least 24%); a bps promise stored as % reads "(20) is below the target (200–400)"
Final: minor (deferred): M6 the panel's h4 skips a level and repeats its aria-label; the 3-line clamp can hide the number the target names, with no expand
Final: minor (deferred): M9 a subsidiary's promise (Tech Mahindra's EBIT margin) leads M&M's card
