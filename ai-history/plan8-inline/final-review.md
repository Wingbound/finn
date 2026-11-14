# Plan 8 final review: 11dad6f..d840f2c (feat/final-polish)

Reviewer: final code review, read-only. I read all 2,807 lines of the package (in four passes), plus the surrounding source the diff touches. Commit 70464ea (docs), which landed after d840f2c, is outside the range and I did not review it.

Verification run on this checkout:
- backend `uv run pytest -q -p no:cacheprovider`: 911 passed
- `ruff check .` and `ruff format --check .`: clean
- frontend `npx vitest run`: 216 passed (14 files)
- `npm run typecheck` and `npm run lint`: clean

Probes I ran myself:
- Ran the other-company filter over every pending ledger row in the seed.
- Timed `company_names`.
- Fed one corrupt dossier row to `attach_promises`.
- Rebuilt the bot's `git pull --rebase -X theirs` in a scratch repo with a depth-1 clone.
- Measured line-clamp overflow of all 51 results-card quotes at the phone's real content width (308 px).

All of these ran from scratch files, outside the repo.

### Strengths

- **Build route (`backend/finn/api/main.py:446-466`).** The change is small and right. A stored dossier of any age is answered from the store. The test is parametrised on age (3 minutes and 3 days). The degraded-rebuild guard is still tested by calling `_build_worker` directly, which is honest about where that guard can still be reached.
- **Other-company filter (`finn/research/link.py`).** On the real seed it drops exactly one row: M&M's "next phase for Tech Mahindra … 15% EBIT margin". No other pending quote across the 23 dossiers matches. `test_on_the_snapshot_mm_card_does_not_quote_tech_mahindra` pins this on the shipped snapshot. The dossier ledger keeps the row, as the plan asks.
- **`seed_changed.py`.**
  - It hashes only the content tables, row by row in primary-key order, over a read-only URI.
  - Classification lives in `filings`, so a reclassification counts as a change.
  - `meta`, `llm_calls` and `llm_cache` are ignored.
  - Tests cover: timestamps only, a new filing, a changed price, and a missing BEFORE.
  - `refresh.py` never deletes rows. `compact_seed.py` touches only `doc_pages` and `doc_text`. So the comparison is like for like.
- **One-off alert window (`page.tsx:58-66`).**
  - Nothing ever writes it to storage. `AlertLog` no longer calls `writeStore`, and `choose` only ever saves the window the reader picked.
  - Dropping the query works without a listener: `setWin` always returns a new state object, and `useSyncExternalStore` re-reads `getSnapshot` on that re-render, so `once` becomes null.
  - On arrival by client navigation, the first render has `ready === false` (`useStored` loads in an effect), so no request goes out for the saved window before the query is read.
  - `encodeURIComponent` keeps the `+05:30` offset intact through `URLSearchParams`.
- **The quiet teaser reuses the main digest's SWR key.** `{hours:168, floor, subscribed}` serialises the same way the main request does, so "Show 7 days" is a cache hit and paints at once. `counts.shown === stories.length` on the backend (`digest.py:139,144`), so the teaser's count is the count the 7-day screen shows.
- **Listen.**
  - One utterance per sentence avoids Chrome's cut-off on long utterances.
  - `speak()` runs inside the click handler, which satisfies the user-activation rules on iOS and Chrome.
  - `u.lang = "en-IN"` is set even when `getVoices()` is still empty, which is the normal first-tap state on iOS and Android.
  - Support is read through `useSyncExternalStore`, so hydration stays consistent.
  - Speech is cancelled on unmount and when the tab is hidden.
  - No spoken figure is computed. Results lines read `yoy_pct` from the card, and `toFixed(1)` matches `pct()` on the card. The only arithmetic is a story count and the window length in hours.
- **Backend robustness.**
  - `refresh.py`: the financials, people and brief stages now fail independently.
  - `people.py`: falls back to the NSE summary and skips noise, mirroring `brief.py:176-180`.
  - `nse_mcp.py`: uses the IST date.
  - `Rules.lookback >= 10`, with the client clamp moved to match, so a stored 5 can't cause a 422.
- **Executor rulings.** I accept all of them: aria-pressed dropped, the caption wording, the visually hidden "Updating" plus dimming, and the source of the name list.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

**1. The bot's rebase silently overwrites any newer snapshot on `main`.**

- **File:** `.github/workflows/refresh.yml:78` (`git pull --rebase --strategy-option=theirs`)
- **What's wrong:**
  - In a rebase, "theirs" is the commit being replayed, which here is the bot's. So when `main` gained a different `seed/finn.sqlite` while the job ran, the binary conflict is resolved in the bot's favour, and the rebase reports success.
  - I reproduced this with a depth-1 clone, which is what `actions/checkout` makes. A human commit of `seed.bin` followed by the bot's `-X theirs` rebase gave "Successfully rebased", and HEAD held the bot's file. The human's snapshot was gone from `main`, though it stays in history.
- **Why it matters:**
  - Case one: a local refresh or dossier/audit fix pushed during a 5-15 minute run is reverted on the live site, with no error anywhere.
  - Case two: under `concurrency: refresh` a queued scheduled run checks out the SHA from when it was triggered, not when it started. GitHub's schedule delays can bunch runs together. Then the second run starts from the pre-first-run seed and clobbers the first run's commit. Anything the first run got and the second didn't (enrichments on an LLM quota miss, a partial price fetch) disappears until a later run redoes it.
  - Before this branch, a plain `git push` would have been rejected instead, which is the safe failure.
  - This is the only path I found by which a run can commit a snapshot that lost data.
- **Fix:**
  - Drop `--strategy-option=theirs`.
  - On a rebase conflict, run `git rebase --abort`, emit a `::notice::` ("main moved; the next run starts from it") and `exit 0`. The next run refreshes from the new `main`.
  - The cheaper alternative: `git fetch origin main` before committing, and skip the commit if `git diff --quiet HEAD origin/main -- seed/finn.sqlite` fails.

**2. "Show more" never appears for quotes of 30 words or fewer, though many of them are clamped on a phone.**

- **File:** `frontend/src/components/today/PromisePanel.tsx:45` (`const long = text.split(/\s+/).length > 30`)
- **What's wrong:**
  - At 390 px the quote's box is 308 px wide: 390 − 2×16 gutter − 36 seen-column − 14 border and padding. At 16 px serif with `line-clamp-3`, that holds roughly 110-130 characters, about 18-22 words.
  - I measured all 51 notes the seed puts on results cards, in a 308 px box. 18 to 25 are clamped, depending on the fallback serif. Between 5 (narrow, Times-like) and 12 (wide, DejaVu Serif) of those have 30 words or fewer and so get no button.
  - Literata sits between those two widths.
  - Examples: ZYDUSLIFE (26 words / 164 chars and 30 words / 176 chars), PERSISTENT (24/146), LODHA (28/148), RELIANCE (21/139), VOLTAS (24/134), MAXHEALTH (22/130).
- **Why it matters:**
  - This was the plan's own Medium bug ("cut to 3 lines with no Show more"), and it is still there on the phone the plan verifies against.
  - A grader sees some quotes end in "…" with nothing to tap, while the quote beside them has "Show more".
  - The vitest passes only because it uses a 108-word quote.
- **Fix:**
  - Measure instead of guessing: use a ref plus `useLayoutEffect` or `ResizeObserver` to set `long = el.scrollHeight > el.clientHeight + 1` while clamped.
  - Or, at minimum, lower the threshold to about 90 characters (`text.length > 90`).

#### Minor (Nice to Have)

1. **The quiet teaser flickers and can briefly show the wrong count.**
   - **File:** `frontend/src/app/page.tsx:84-86,140-145`
   - **First load:** on a quiet day (which tomorrow, a Sunday, will be) the screen first shows "Nothing at this level. Lower the bar to Everything, or widen the window." for the length of the second request, then swaps to the teaser.
   - **Wrong count:** `useDigest` has `keepPreviousData: true`, so after a floor or category change `week.data` is still the old key's digest. The teaser shows, say, "26 things mattered" (Important) for a second before it settles on the Critical count.
   - **Wrong label:** switching 24h to 3d on a quiet day shows "Quiet 3 days." over the still-loading 24-hour data.
   - **Fix:** while `week.isLoading` (or `week.isValidating`), render nothing (or the teaser without its count line). Give the week request its own SWR call without `keepPreviousData`. Show the teaser only when `!isValidating`.

2. **Stripping a bare "India" turns some company names into common words.**
   - **File:** `backend/finn/research/link.py:37`
   - **What's wrong:**
     - `Coal India Ltd` becomes {"coal india", "coal"}. Likewise `Oil India` gives "oil", `Bank of India` gives "bank of", `Engineers India` gives "engineers", and `ABB India` gives "abb".
     - Dossier names feed the list, and a live build is saved on its Vercel instance. So a grader who builds COALINDIA (a Nifty 50 name, a likely test) makes "coal" an other-company name on that instance.
     - Tata Steel's card then loses its pending promise about coking coal. The seed has one such row.
   - **Impact:** it fails toward hiding a note, and only on that instance, hence Minor.
   - **Fix:** strip only a parenthesised "(India)". Or keep a stripped form only when it still has two or more words, or when it is the name minus "Ltd".

3. **One corrupt dossier row now 500s the whole digest.**
   - **File:** `backend/finn/research/link.py:56`
   - **What's wrong:** `json_extract` over every dossier raises `sqlite3.OperationalError: malformed JSON` when any one `payload_json` is invalid. I verified this. `attach_promises` doesn't catch it, so `/digest` returns 500.
   - **Why it matters:** this regresses the Plan 6 M5 guarantee that a corrupt dossier costs only that symbol its notes. `test_a_corrupt_dossier_gives_no_notes` misses it because there `get_dossier` fails first and `company_names` is never reached.
   - **Cost:** about 10 ms per digest on the seed (23 payloads, ~8 MB of JSON parsed), and twice per visit on a quiet day.
   - **Fix:** add `WHERE json_valid(payload_json)`, or wrap the query in `try/except sqlite3.Error`. Cache on `(count(*), max(built_at))`.

4. **A crash of `seed_changed.py` reads as "no new data".**
   - **Files:** `backend/scripts/seed_changed.py:55-57`, `.github/workflows/refresh.yml:69`
   - **What's wrong:**
     - A traceback exits 1, so the step logs "No new data; the snapshot is not committed."
     - An unreadable AFTER (`new is None`) counts as changed. `compact_seed` would normally fail first, so this is latent.
   - **Fix:** use a distinct exit code for "unchanged" (for example 3), treat anything else as failure, and treat `new is None` as an error.

5. **Listen has four robustness gaps on real phones.**
   - **File:** `frontend/src/components/today/ListenButton.tsx:38-49`
   - (a) `synth.cancel()` runs unconditionally right before `speak()`. On some Chrome builds, a speak issued straight after a cancel is dropped. Cancel only when `synth.speaking || synth.pending`.
   - (b) The utterances aren't kept anywhere. Chromium has a long-standing bug where `onend` never fires for a garbage-collected utterance, so the button can stay on "Stop listening" after the voice ends. Keep them in a ref.
   - (c) Some Android builds report `en_IN`. That misses `=== "en-IN"`, falls to the first `en*` voice, and overrides the `en-IN` lang. Normalise with `_` → `-`.
   - (d) Changing the window mid-speech keeps reading the old brief. Stop when `lines` changes.

6. **The spoken window and rounding can mislead.**
   - **File:** `frontend/src/lib/briefScript.ts:16-21,28-31`
   - **Window:** any range of exactly N days is read as "the last N days". The alert week (`?from=&to=`) or a custom range that ended days ago is announced as recent. Say "this window" unless `window.end` is within an hour of now or `as_of`.
   - **Rounding:** `move(0.04)` reads "up 0.0 percent". Treat |v| < 0.05 as "flat".

7. **Test gap: nothing exercises leaving a one-off window.**
   - **Files:** `frontend/e2e/alerts.spec.ts`, `frontend/tests/alerts.test.tsx`
   - **What's wrong:** no test arrives on `/?from=&to=`, taps "24 hours", and asserts that the URL is `/` and storage holds `{hours:24}`. The e2e checks the saved window with a fresh `page.goto("/")`, which never drives `choose` and `replaceState`. My reasoning says the code works; nothing pins it.

### Answers to the five review-focus questions

1. **Today window.**
   - Picking a window does drop the query, on a fresh load and after client navigation. `replaceState` doesn't notify the store, but the `setWin` re-render re-reads the snapshot.
   - The one-off window is never saved. Only a deliberate pick is saved, including StaleNotice's "Show the week up to …".
   - The 7-day request goes out only when `quiet` is true; otherwise its key is null.
   - The counts are right once both digests have landed. The flicker and stale-count cases are Minor 1.
2. **Build route.**
   - No reader path is lost. The UI never offers a rebuild of a stored dossier: there is no Rebuild button, and SearchBox links known symbols without `?build=1`. Before this change, the only ways to rebuild a stored dossier were the race and the `?build=1` reload, which are the very bugs this branch fixes.
   - A degraded first live build stays degraded on its instance until the instance recycles, as it effectively did before.
   - "Try again" after a client timeout now gets the saved copy instantly, when it lands on the instance that built it.
3. **Link filter.**
   - The seed has no false positives.
   - The generic-word risk comes from stripping a bare "India" (Minor 2).
   - Names inside the company's own name are handled. The substring test can only weaken the filter, never cause a false drop.
   - The cost is about 10 ms per digest, plus the corrupt-row 500 (Minor 3).
4. **Workflow.**
   - `set +e` is scoped to the Refresh step, and the `cp` runs before the refresh.
   - `compact_seed` changes nothing the hash reads.
   - `git checkout --` is harmless.
   - Commit-on-change behaves as intended.
   - `-X theirs` is the data-loss path (Important 1).
5. **Listen.**
   - The basics hold: speech starts in the click handler, `lang` works as a fallback when no voices are loaded, sentences are queued as separate utterances, and speech stops on unmount and when the tab is hidden.
   - No spoken figure is computed. Minor 5 and Minor 6 cover the remaining edges.

### Declined to judge (set aside, one line each)

- iOS mutes Web Speech when the ring/silent switch is on silent. This is platform behaviour; the plan has no hint text for it.
- Live builds are cached per instance, and a retry on another instance rebuilds. This is a known gap listed in CLAUDE.md, not changed here.
- "Show 7 days" in the teaser saves 7 days as the reader's window. It matches StaleNotice's existing presets, which also save, and is a deliberate tap.
- The Custom sheet ignores the current range. The plan lists it as Low and assigns it to no task.
- On each focus revalidation the list dims instead of showing a line. This replaces the old "Updating" line, which appeared at the same moments, so it is not a regression.
- The `buildDossier` deadline doesn't abort the underlying fetch, and the `!res.ok` body read isn't raced. These are cosmetic, since the reader already sees the timeout state.
- Commit 70464ea (docs) is outside the review range.
- The items in the plan's "Not doing" list (SSE id match, NFKC ligatures, SW cache versioning, segmented-control a11y, the 2% pace tolerance) are out of scope by the plan.

### Plan alignment

- The quiet teaser is its own component (`QuietTeaser.tsx`) rather than an extension of `StaleNotice`. This is justified: "not empty but quiet" is a different state from "empty". `isEmptyWindow` lives in StaleNotice, as asked.
- The copy differs slightly from the plan ("Over the last 7 days, N things mattered.") and reads better.
- `aria-pressed` was dropped from Listen, as ruled.
- Listen reads at most 6 stories, then "And N more on screen", which keeps it near 60 s. This is reasonable.
- The plan's "results" table maps to `financials`. That is correct.
- All of Tasks 1-5 are present. Tasks 6-7 (live checks, docs, history) are outside this range.

### Recommendations

- Fix Important 1 before the next scheduled run. It is a one-line change, and the user will push to `main` again (merge, ai-history) while the bot runs six times a day.
- Fix Important 2 with a measured overflow. It is one component, and the e2e at 390×844 can assert it.
- Minor 1 and Minor 3 are each a few lines, and both fall on the path a grader takes on a quiet Sunday.

### Assessment

**Ready to merge: With fixes**

**Reasoning:** The branch delivers every Plan 8 item, and all suites are green. The two Important issues are a silent snapshot-overwrite path in the new rebase step and a "Show more" heuristic that misses roughly 10-25% of results-card quotes at phone width. Both are small, local fixes.
