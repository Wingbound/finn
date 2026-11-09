# SDD ledger — plan: docs/superpowers/plans/2026-11-09-plan4-frontend.md
Spec: docs/DESIGN.md §1 Surfaces + §7b; Plan 3 product notes restated in the plan's Global Constraints.
Executor: inline (superpowers:executing-plans) on branch feat/frontend from main fcfb2b3.
- Ruling P4-R1: inline execution instead of subagent-driven — the UI tasks share one design system and components (tightly coupled), and coherence needs one hand; one opus whole-branch review at the end — cost if wrong: no per-task reviewer, so defects surface only at the final review.
Pre-flight (shared interfaces):
| producer → consumer | produced | consumed | finding |
|---|---|---|---|
| T0 → T2..T6 | types.ts + fixtures | api hooks, components, tests | /research list `counts` has no status tally, but T5's DossierList needs one → Ruling P4-R2 |
| T2 → T3..T6 | api/store/format/sse | screens | consistent |
| T5 → T6 | done payload {dossier, excerpts} into the SWR cache | SourceSheet reads excerpts or /source | consistent; excerpts keyed {source_id: {page: text}} |
| T3 → T6 | "Dig in" → /research/{symbol} | dossier page 404 → offer a build | the plan doesn't say what Dig in does without a dossier → Ruling P4-R3 |
- Ruling P4-R2: Task 0 adds `ledger: d.ledger.counts` to the backend's `/research` list `counts` (a one-line backend change beyond the export script) — the list needs the tally and the backend already has it — cost if wrong: one field.
- Ruling P4-R3: Dig in on a symbol without a dossier opens the research page for that symbol with a "Build a dossier" button (the same live build as search) — cost if wrong: one extra tap.
- Ruling P4-R4: symbols are URL-encoded everywhere (M&M is in the portfolio) — Review Focus addition; cost if wrong: none.
Setup note: T1 scaffold, T0's types.ts and export script, and T2's format.ts/store.ts were written during planning, before this ledger and before the TDD gate. Their tests are written now and each is mutation-checked (break the code → watch the test fail → restore).
- Task 0: Ruling: the frontend test tooling (package.json, vitest config, setup) is committed with Task 0, because Task 0's fixture test needs it and the plan put it in Task 1 — cost if wrong: none (commit grouping only).
Task 0: complete (commits fcfb2b3..a51ba63, tests: bash -c 'cd backend && uv run pytest -q && cd ../frontend && npx vitest run' →    Duration  544ms (environment 69%, setup 16%, tests 9%, import 3%, transform 2%, worker 1%))
Task 1: complete (commits a51ba63..2a17d5b, tests: bash -c 'cd frontend && npx vitest run && npx playwright test' →   3 passed (4.6s))
Task 2: complete (commits 2a17d5b..e120b64, tests: bash -c 'cd frontend && npx vitest run' →    Duration  691ms (environment 71%, setup 17%, tests 7%, import 2%, transform 1%, worker 1%))
- Task 3: Ruling: the bank-card test uses the NBFC fixture (BAJFINANCE) — the 7-day snapshot holds no bank results; the NBFC format exercises the same "no EBITDA row" path — cost if wrong: the bank layout is untested in the UI (it is tested in the backend).
- Task 3: Ruling: Mark seen is a check circle in the card's left margin, not a footer button — five footer actions don't fit 358 px; ticking off fits the editor metaphor — cost if wrong: discoverability (it has an aria-label and aria-pressed).
- Task 3: Ruling: results deltas stay in ink, not green/red — a rising credit cost is not good news — cost if wrong: less glanceable.
- Task 3: Ruling: added cleanSubject (format.ts) to strip NSE's "has informed the Exchange about" boilerplate — found in screenshot review — cost if wrong: none (the original subject is kept when the pattern doesn't match).
- Task 3: Ruling: a stub /research/[symbol] route lands now so Dig-in prefetches don't 404 (Task 6 replaces it).
Task 3: complete (commits e120b64..336c577, tests: bash -c 'cd frontend && npx vitest run && npx playwright test' →   6 passed (5.2s))
- Task 4: Ruling: the alert log shows the newest 8, with "Show all N" — 43 alerts a week buried the holdings (the Plan 3 note on alert volume) — cost if wrong: one tap to see the rest.
- Task 4: Ruling: filing alerts show their category, read from story_id ("SYM:category:seq"), instead of "Filing", and entity-decoded text (NSE leaves "&#8377;" in subjects) — cost if wrong: none.
- Task 4: Ruling: the sparkline tooltip says "N sessions back", not a date — /portfolio sends closes without dates — cost if wrong: less precise hover (a backend field would fix it).
Task 4: complete (commits 336c577..be6750f, tests: bash -c 'cd frontend && npx vitest run && npx playwright test' →   8 passed (5.3s))
- Task 5: Ruling: BuildProgress lives on the dossier route — picking a symbol with no dossier goes to /research/SYM?build=1, which starts the build; on done the dossier renders in place (no second navigation), so "on done it routes" becomes "on done it hands the dossier to the page" — one place for builds, a shareable URL, and Dig-in from Today reuses it (P4-R3) — cost if wrong: none visible.
Task 5: complete (commits be6750f..cfcdef6, tests: bash -c 'cd frontend && npx vitest run && npx playwright test' →   11 passed (6.7s))
- Task 6: Ruling: Track record (earlier calls) comes before Open promises — the plan listed Open first, but the delivered-vs-promised verdicts are the point and the open rows are all pending; resolved rows lead each group — cost if wrong: reorder two blocks.
- Task 6: Ruling: when two transcripts share a quarter (BAJFINANCE has two Q4 FY26 calls, Apr and May 2026), chips add the month ("Q4 FY26 call (May 2026), p. 4") — cost if wrong: none.
- Task 6: Ruling: the source sheet reflows PDF hard line breaks before matching and showing — the raw text broke sentences mid-line — cost if wrong: page layout differs from the PDF (the PDF link is one tap away).
- Task 6: Note: the seed dossiers record the cached rebuild that applied the Task 7g guards, so their cost line reads "Served from cache"; EVALS §4 keeps the first-build costs.
Task 6: complete (commits cfcdef6..b144b96, tests: bash -c 'cd frontend && npx vitest run && npx playwright test' →   13 passed (6.1s))
- Task 7: Ruling: the worker also caches POST /digest and /alerts under a synthetic GET key carrying the body — Today is the screen worth having offline, and it is a POST — cost if wrong: one cache entry per distinct request body (small).
- Task 7: Ruling: Playwright blocks service workers by default (page.route can't see worker fetches); the offline test opts back in and mocks on the context — cost if wrong: none.
- Task 7: Ruling: the axe sweep also runs in dark mode (the plan said light only) — cost if wrong: none.
Task 7: complete (commits b144b96..f8723c4, tests: bash -c 'cd backend && uv run pytest -q && cd ../frontend && npx vitest run && npx playwright test' →   31 passed (10.1s))
Final review (opus): ready to merge with fixes — C1, I1-I5, M1-M13. No ruling judged wrong (the Task 5 ruling led to I3 and M1).
- Final: Ruling: M3 re-graded to Important — the plan's Global Constraint says absolute times beyond 24 h, and an analyst needs the timestamp — cost if wrong: none.
Final: fixed C1 — hooks.test "keep showing after a build even when the server's copy 404s" RED→GREEN
Final: fixed I2 — store.test "keeps a saved setting for the session when a new screen mounts" RED→GREEN
Final: fixed I3 — sse.test "drops mid-body…incomplete" + "skips a malformed frame", research.test "offers to look for the saved copy" + "unexpected failure…stopped" RED→GREEN
Final: fixed I1 — e2e "failed refresh after a window change" + "failed refresh after saving rules" RED→GREEN
Final: fixed I4 — today.test "only offers presets that reach…" + "offers the week up to…" RED→GREEN
Final: fixed I5 — alerts.test "open Today on the alert log's own window", e2e "routine story opens the drawer" + "outside the window says so" RED→GREEN (the earlier "7-day view" e2e was updated to the new window)
Final: fixed M3 — today.test "relative within a day and absolute beyond it" RED→GREEN; suite 132/132 vitest, 35/35 Playwright, 758/758 pytest
Final: minor (deferred): M1 ?build=1 skips the stored-dossier check (a known company picked while the list loads rebuilds; a reload after Cancel rebuilds)
Final: minor (deferred): M2 partly addressed by the I5 change (a garbled hash is ignored, scrolling happens once); the "Updating" line still shifts the layout
Final: minor (deferred): M4 tap targets under 44 px (citation chips 32 px, segmented 40 px, some text links)
Final: minor (deferred): M5 the build screen's live region announces the elapsed counter every second
Final: minor (deferred): M6 small a11y nits (aria-label on a span, radios without arrow keys, Mark seen changes both its label and its pressed state, toast region, chart readouts announced on hover, smooth scroll under reduced motion)
Final: minor (deferred): M7 seen cards flash in rank order before sinking, on load
Final: minor (deferred): M8 service worker: no fallback on 5xx or timeout, a fixed version (no pruning of old static files), no data-cache cap, assumes the API sits at the origin root
Final: minor (deferred): M9 the highlight misses quotes that need NFKC normalisation (ligatures) or span a page break
Final: minor (deferred): M10 /research/%E0%A4%A returns a 500
Final: minor (deferred): M11 the 15 s timeout covers only the headers, not the body
Final: minor (deferred): M12 build errors show raw server strings ("build failed: RuntimeError")
Final: minor (deferred): M13 unruled deviations and copy (900 ms stroke, 14 px sheet radius, "4 filings" without "in this story", volume ratio shown only over the limit, "1 promises tracked")
