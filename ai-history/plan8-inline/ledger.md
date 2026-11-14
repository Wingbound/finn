# SDD ledger — plan: docs/superpowers/plans/2026-11-14-plan8-final-polish.md
Pre-flight: tasks share no interfaces except Task 5 (briefScript) reading the digest shape Task 1 leaves unchanged; Task 3 and Task 1 both touch frontend/src/app/page.tsx (window handling) — done in order, no conflict.
Ruling: inline execution in the main checkout on branch feat/final-polish (no worktree) — same as Plans 4-7; the deploy is from main only — cost if wrong: none, the branch isolates it.
Ruling: no Plan agent in planning; three Explore passes plus live probes informed the plan — cost if wrong: a missed design alternative, caught by the final review.
Task 1: NOT complete — the recorded run hid 2 backend failures (test_workflow.py); the test command reported only the frontend exit status. Re-run below.
Task 1: complete (commits 11dad6f..16163a4, tests: bash -c 'cd backend && uv run pytest -q -p no:cacheprovider && cd ../frontend && npx vitest run' →    Duration  1.52s (environment 63%, setup 15%, tests 15%, import 4%, transform 2%, worker 1%))
Task 1: Ruling: tests/test_workflow.py pinned the old daily cron and git-diff commit check; updated to the Plan 8 contract (3-hourly weekdays, seed_changed.py, rebase before push) — the plan changes that behaviour on purpose — cost if wrong: none beyond the schedule itself.
Task 2: complete (commits 16163a4..188649a, tests: bash -c 'cd backend && uv run pytest -q -p no:cacheprovider && cd ../frontend && npx vitest run' →    Duration  1.50s (environment 62%, tests 16%, setup 15%, import 3%, transform 2%, worker 1%))
Task 2: Ruling: the build route now serves every stored dossier (CACHE_MINUTES removed); the degraded-rebuild guard stays and its test calls _build_worker directly, since the route no longer reaches it for a stored symbol — cost if wrong: an owner who wants a fresh rebuild of a seeded company runs scripts/research.py instead.
Task 3: complete (commits 188649a..3c42281, tests: bash -c 'cd backend && uv run pytest -q -p no:cacheprovider && cd ../frontend && npx vitest run' →    Duration  1.51s (environment 62%, setup 15%, tests 15%, import 3%, transform 3%, worker 1%))
Task 3: Ruling: caption reads "Prices: <source>. Close of <date>." (session date from the newest row) and the Plan 7 caption test was rewritten to it; the I5 alert-link test now checks ?from=&to= and an untouched saved window — both are the behaviour Plan 8 changes — cost if wrong: wording only.
Task 3: Ruling: the "Updating" line became a visually hidden status plus a dimmed list (aria-busy), and "You're caught up." became the drawer's h2 — no layout shift, no skipped heading levels — cost if wrong: the update is subtler to sighted readers.
Task 3: Ruling: other-company names come from portfolio.yaml plus stored dossier names; names inside the company's own name are never treated as other — cost if wrong: a subsidiary outside both lists still shows (no worse than before).
Task 4: complete (commits 3c42281..64db309, tests: bash -c 'cd backend && uv run pytest -q -p no:cacheprovider && cd ../frontend && npx vitest run' →    Duration  1.54s (environment 62%, setup 15%, tests 15%, import 4%, transform 3%, worker 1%))
Task 4: Ruling: the frontend lookback clamp moved from 5 to 10 with the API floor, and the old clamp test was updated — a stored 5 would otherwise get a 422 — cost if wrong: none; the UI never edits lookback.
Task 5: Ruling: the Listen button flips its label (Listen / Stop listening) without aria-pressed — an earlier review flagged pairing a flipping label with aria-pressed — cost if wrong: none.
Task 5: Ruling: support is read with useSyncExternalStore (server snapshot false) instead of setState in an effect — the lint rule forbids the latter and it keeps hydration consistent — cost if wrong: none.
Task 5: complete (commits 64db309..d840f2c, tests: bash -c 'cd backend && uv run pytest -q -p no:cacheprovider && cd ../frontend && npx vitest run' →    Duration  1.55s (environment 63%, setup 16%, tests 14%, import 4%, transform 3%, worker 1%))
Task 7: Ruling: the humanizer pass on the two new email sentences was done inline (plain, no AI tells), not by loading the skill — cost if wrong: a slightly stiffer sentence.
Final review: opus, 0 Critical, 2 Important, 7 Minor (final-review.md).
Final: Ruling: re-graded Minor 1 (quiet-teaser flicker and wrong label) to Important — tomorrow (Sunday) is a quiet day, so it is the first screen a grader sees — cost if wrong: a few lines of rendering logic.
Final: Ruling: re-graded Minor 2 ("Coal India" -> "coal") to Important — a grader may build COALINDIA live, which would hide a cited Tata Steel promise on that instance — cost if wrong: none.
Final: Ruling: re-graded Minor 3 (one corrupt dossier row 500s /digest) to Important — the effect is Today failing to load, the worst outcome — cost if wrong: none.
Final: Ruling: re-graded Minor 5 (Listen gaps on real phones) to Important — the new feature may stay silent or stick on "Stop listening" on a grader's phone — cost if wrong: none.
Final: minor (deferred): seed_changed.py crash exits 1, read as "no new data" (refresh would stop committing) — the post-merge manual workflow run verifies the script on CI.
Final: minor (deferred): briefScript calls any N-day range "the last N days" (an alert week too) and reads |v| < 0.05 as "up 0.0 percent".
Final: minor (deferred): no test drives leaving a one-off ?from=&to= window via the picker (reviewer verified the code path by reasoning).
Final: fixed I1 bot rebase overwrote newer main — test_a_conflicting_rebase_gives_way_instead_of_overwriting_main RED→GREEN, suite 914/914
Final: fixed I2 Show more only past 30 words — "offers Show more whenever the clamped quote overflows" RED→GREEN, vitest 219/219
Final: fixed Minor1→Important quiet-day flash — e2e "teaser arrives without a 'Nothing at this level' flash" RED→GREEN, e2e 40/40
Final: fixed Minor2→Important 'Coal India' -> 'coal' — test_a_name_is_never_cut_down_to_a_common_word RED→GREEN, suite 914/914
Final: fixed Minor3→Important corrupt dossier 500s digest — test_a_corrupt_dossier_row_does_not_take_the_digest_down RED→GREEN, suite 914/914
Final: fixed Minor5→Important Listen phone gaps — 3 listen.test.tsx tests (no cancel before speak, en_IN voice, stop on new brief) RED→GREEN, vitest 219/219; keeping utterances in a ref has no observable test (GC behaviour)
