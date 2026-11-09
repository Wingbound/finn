# SDD ledger — plan: docs/superpowers/plans/2026-11-10-plan5-deploy.md
Spec: docs/DESIGN.md Hosting, Robustness, §8; PROJECT_BRIEF §9.
Executor: inline (superpowers:executing-plans) on feat/deploy from main a58cdb4.
Pre-flight: T1 → T2 (index.py entry, ALLOWED_ORIGINS, /health seeded+cors) consumed by the live checks; T1 → T3 (refresh exit 2 = no commit) consumed by the workflow. Consistent.
Task 1: measured `import finn.api.main` warm: 1.52 s before, 0.60 s after.
- Task 1: Ruling: pandas and yfinance moved to a "refresh" dependency group (default-groups keeps local and CI installs whole) — the plan only asked for lazy imports, but Vercel installs [project] deps, so this also shrinks the bundle by ~100 MB — cost if wrong: a job that forgets the group lacks pandas (the CI workflow installs default groups).
- Task 1: Ruling: the seed helpers moved to finn/api/seed.py (deps.py needs them, and main imports deps); main re-exports copy_seed_if_empty — cost if wrong: none.
Task 1: complete (commits a58cdb4..849ce46, tests: bash -c 'cd backend && uv run pytest -q' → 769 passed in 28.93s)
- Task 3: Ruling: actions/checkout@v7 and astral-sh/setup-uv@v10 (current majors from the GitHub API, 2026-11-10) — cost if wrong: a major bump in a workflow file.
- Task 3: Note: the live workflow_dispatch run waits for the repo and its secrets (user steps).
Task 3: complete (commits 849ce46..9b7d904, tests: bash -c 'cd backend && uv run pytest -q' → 774 passed in 28.49s)
- Task 2 step 1 (security pass, 2026-11-10): 107 commits, 0 key-pattern hits (AIza, gsk_, hf_, sk-, ghp_, vercel_, private keys), 0 student-ID-pattern hits; the email appears only as the commit author (Wingbound <user gmail>), never in file contents → ask the user before the first push; 2 home paths in archived briefs redacted to repo-relative. Tracked files: .env.example and a test PDF only.
- Task 4: exporter run on the main session: 0.4 MB, 17 user turns; leak scan clean except my own scan patterns and the user's first name (kept: it is their submission). Output waits in the scratchpad for the user's review.
- 2026-11-10: User chose GitHub's private address. All 109 commits were rewritten (filter-branch: author and committer = Wingbound@users.noreply.github.com), the trees were verified identical, refs/original was dropped and objects pruned. 0 occurrences of the Gmail in history. Repo-local user.email is set to the noreply address. NOTE: every commit hash in the ledgers and ai-history from before this point refers to the pre-rewrite history.
- 2026-11-10: the user approved a public repo; created github.com/Wingbound/finn and pushed main (b08d61e). feat/deploy was merged and deleted; the remaining Plan 5 work (live checks, email) continues from main.
- Task 2: deployed. Frontend https://finn-qx98.vercel.app, API https://finn-peach.vercel.app (the user imported both in the Vercel dashboard and typed the keys and ALLOWED_ORIGINS there). /health: seeded true, cors = frontend only; a foreign preflight gets a 400. Warm endpoints 0.3-0.8 s, search 1.0 s.
- Task 2: live builds: ASIANPAINT about 75 s (the curl HTTP/2 client lost the tail; it was saved; a retry got the cache in 0.37 s); TITAN 75 s streamed cleanly over HTTP/1.1 with pings on time; PIDILITIND 83 s through the UI in Chromium. e2e-live passes (tabs, citation highlight).
- Task 2: Ruling: no resume endpoint for dropped builds — the browser path streamed fine, and the existing "Check for a saved copy" covers drops — cost if wrong: a phone that drops mid-build may rebuild on another instance (one more build of about 9 calls).
Task 2: complete (live checks recorded above; commits 3527257, fc399f3)
- Task 3: the first run failed (setup-uv@v10 does not exist; full tags only) → pinned v10.3.0. Run 42697807536 succeeded: 5 filings, 1,134 bars, 0 errors, 3.2 MB, committed by github-actions[bot] (76b0d6d). NSE does not block GitHub runners.
- Task 4: README has the live links; EVALS §5 covers the deployment; the email draft (humanized) is in the scratchpad; the AI-history export waits for the user's review.
Final review (opus + security): ready with fixes. No Critical; I1 build endpoint has no cap or symbol validation; I2 a refresh crash exits 1 = "partial" and commits a recompacted unchanged seed; I3 exporter redaction gaps (clip before redact, \b next to _, case, escaped emails, Windows and dashed paths, more key shapes). Minors M1-M13.
- Final: Ruling: M2 re-graded to Important — Review Focus 4 requires a bad ALLOWED_ORIGINS to fail loudly in /health — cost if wrong: none.
- Final: Ruling: M9 re-graded to Important — Task 2 asked the live spec to check /health and record the cold-start time — cost if wrong: none.
- Final: Ruling: M11 re-graded to Important — the user asked that personal identifiers stay out of the public repo; the OS username is one — cost if wrong: none.
- Final: Ruling: M10's notification and allowlist parts are fixed with I3 (same code, same tests); rendering subagent transcripts is included because they are part of the build history.
Final: fixed I1 — test_api_research "non_symbols_are_rejected…", "second build of the same symbol…refused", "builds stop at the hourly cap", "api docs hidden on vercel"; frontend sse.test "show the server's reason for a 400" RED→GREEN
Final: fixed I2 — test_deploy "refresh_crash_is_not_partial" (exit 4, untouched, no temp files) and test_workflow "only clean or partial refreshes go on to commit" RED→GREEN
Final: fixed M2 (re-graded) — test_deploy "health_flags_bad_cors_settings" RED→GREEN
Final: fixed I3 (+ M10's notification, allowlist and subagent parts) — test_export_history: 13 leak probes, the anchored allowlist, private literals file, redaction before clipping, notifications, subagent transcripts; 18 RED→GREEN. The real session re-exported with FINN_REDACT_FILE (scratchpad/redact.txt, never committed): 0 email, username, entry-number or key hits.
Final: fixed M9 (re-graded) — e2e-live "API is seeded, allows exactly this site…" RED against the old deploy (no cors_problems); GREEN pending the new deploy
Final: fixed M11 (re-graded) — DESIGN.md:226 path now ~/.claude/projects/<project>/; git grep finds no username
Suite after the pass: pytest 803/803, vitest 133/133, Playwright 35/35; merged as 3c6e4d2 and pushed.
Final: minor (deferred): M1 the seed copy is not atomic; a half-copied store isn't retried
Final: minor (deferred): M3 a missing LLM key in CI exits 0 with no warning
Final: minor (deferred): M4 refresh temp files not gitignored (the crash path now deletes them); a refresh into the live serving DB loses concurrent writes
Final: minor (deferred): M5 workflow hardening (persist-credentials, SHA pins, rebase before push)
Final: minor (deferred): M6 the README's local fallback skips compact_seed.py
Final: minor (deferred): M7 a leftover getattr on a key field (router.py:125; works through SecretStr.__len__)
Final: minor (deferred): M8 the 285 s guard assumes a 300 s maxDuration that no vercel.json pins (Vercel's Hobby default is 300 s)
Final: minor (deferred): M12 /research/search has no length cap and echoes upstream error text
Final: minor (deferred): M13 a daily commit and redeploy even with no new data wipes live builds daily
Final: M9 live check GREEN on the new deploy (/health 396 ms, cors exact, no problems). Plan 5 complete; the AI-history publish waits for the user's review.
