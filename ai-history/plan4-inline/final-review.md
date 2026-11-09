# Plan 4 (frontend) final review: fcfb2b3..f8723c4

Reviewer: final whole-branch review (read-only). Branch `feat/frontend`, HEAD f8723c4.

## What I ran

- `npx vitest run`: 11 files, 122 tests pass.
- `npx tsc --noEmit` and `npx eslint .`: clean.
- `npx playwright test`: 31 pass, 20 skipped (the screenshot specs).
- Browser probes against the production build (`next start`, API mocked from the fixtures, scripts in my scratchpad; no repo files touched):
  - a failed refetch after a window change;
  - blocked and corrupt `localStorage`;
  - a live build whose follow-up GET returns 404;
  - M&M links and routes;
  - a malformed dossier URL.
- Node probes of `buildDossier` (a stream that drops mid-body, and a malformed frame), and of `findQuote` over every captured source page.

## Strengths

- **A small, careful library layer.** `api.ts`, `store.ts`, `format.ts` and `sse.ts` are small and well separated. Validators clamp to the backend bounds. Seen marks are capped. Every formatter returns "–" for null or NaN, so no screen can print NaN.
- **The SSE parser is solid.** It handles CRLF, comment pings, multi-line data and a whole buffered body, and it is tested against a real captured stream.
- **Fixtures come from the real backend.** `types.test.ts` checks the shape of every fixture field by field, so a backend change fails a test.
- **Provenance typography is implemented faithfully.** Literata is used only for promise and evidence quotes, grounded people profiles, grounded brief quotes and the source page. FACTS chips read "Computed from filed financials", and the FACTS sheet sets the line in Plex with the "not quoted from a document" note. A test covers this. I found no place where a computed number is presented as a quote (computed ledger rows carry no evidence in the backend).
- **Partial dossiers.** Each section renders a `SectionNote` when it is null. The note regexes match the backend's real note strings (`pipeline.py`, `synthesis.py`). Lenders get "Financing margin" and no CFO/PAT row.
- **M&M is encoded correctly end to end.** In the browser, the Holdings link is `/research/M%26M`, the API call is `/research/M%26M`, the heading reads "M&M", and `/research/m%26m` works.
- **Accessibility basics are in place.** Sheets are native `<dialog>`s. Tabs carry `aria-current`. Every status has a glyph and a word. axe runs at 390 and 360 px in light and dark, plus inside both sheets, along with overflow and console-error checks on every screen.
- **The service worker is conservative.** It never caches `/build`, never caches non-OK responses, and does not cache the SSE stream. It tags fallback copies so the UI can say they are offline copies.

## Critical (must fix)

### C1. A live-built dossier is replaced by "FINN hasn't read this company yet" when the follow-up GET returns 404

- **Where:** `src/lib/hooks.ts:19-26,62-66` (`useDossier`, where `orNull` maps 404 to `null`); `src/lib/hooks.ts:85-89` (`primeDossier` primes the cache, but SWR still revalidates on mount and on focus); `src/components/dossier/DossierScreen.tsx:24-28,43-56`.
- **Scenario:** a live build of NEWCO streams `done`. `primeDossier` seeds the cache, and `router.replace("/research/NEWCO")` runs. `useDossier("NEWCO")` mounts and revalidates (`revalidateIfStale` defaults to true), and `GET /research/NEWCO` returns 404. The user sees the dossier for a moment, then the page shows "NEWCO. FINN hasn't read this company yet… Build a dossier."
  - The probe reproduced this: the final URL is `/research/NEWCO`, the h1 is "NEWCO", there is no ledger heading, and the "Build a dossier" button is showing.
- **Why it is likely:**
  - Plan 5 (`docs/superpowers/plans/2026-11-10-plan5-deploy.md:16`) keeps live builds in "a per-instance copy in /tmp". The GET that follows a build (or any later focus revalidation) can land on another instance or on a recycled one.
  - The backend also logs and swallows a failed save, on purpose: "a failed save cannot cost the client its dossier" (`main.py` `_build_worker`).
  - Plan 5's own live check ("one live build of an unseen ticker through the deployed UI") is the path that breaks.
- **Fix:**
  - Treat a dossier from a live build as authoritative on the client. For example, keep it under its own SWR key (`["built", SYM]`, no fetcher), and have `DossierScreen` render `data ?? built`.
  - Alternatively, make the `useDossier` fetcher return the current cached dossier instead of `null` on a 404 when one was primed.
  - Add a vitest or Playwright case: build done, then GET 404, and the dossier must still render.

## Important (should fix)

### I1. A failed refetch leaves the previous answer on screen under the new label, with no error

- **Where:** `src/app/page.tsx:71` (`error && !data`) together with `keepPreviousData: true` in `src/lib/hooks.ts:32,44`; `src/app/alerts/page.tsx:50`.
- **Scenario:** Today has loaded 24 h. The user taps "7 days", and the server is unreachable or times out.
  - The probe showed the 7 days radio checked, the h1 still reading the 24 h headline "7 things matter", and no "Couldn't reach FINN's server". The "Updating" line disappears once the request fails, so the screen looks like a successful 7-day answer.
  - The same happens on Alerts after "Save rules": the header states the new rules over the old alert list.
  - Review Focus 2 wants stale data kept visible, but together with the error.
- **Fix:**
  - When `error && data`, render a compact `ErrorState` (with Retry) above the kept content.
  - Alternatively (or as well), label the content with the window it answers, from `data.window`, so the user can see that the stories are the 24 h ones.

### I2. With storage blocked, saved rules (and window, floor and seen marks) are lost on every tab switch

- **Where:** `src/lib/store.ts:99-118` (`readStore`/`writeStore` have no in-memory fallback) and `:130-135` (each `useStored` mount re-reads storage).
- **Scenario:** `localStorage` throws, as it does with site data blocked or in some embedded or private contexts. The probe ran these steps:
  1. On Alerts, set the volume to 1 and tick Dividend, then save. The header reads "Volume over 1×… 8 filing types".
  2. Switch to Today. The digest request goes out with the 7 default categories and no `dividend`.
  3. Switch back to Alerts. The header reads "Volume over 2×… 7 filing types".

  Review Focus 3 requires that "saving rules still works for the session". It works only while the Alerts page stays mounted. The unit test (`tests/store.test.ts:97`) checks a single mounted hook, so it misses this.
- **Fix:** keep a module-level `Map` as a fallback. `writeStore` always writes the Map. `readStore` returns the Map value when storage throws or holds nothing newer. Add a test that unmounts and remounts the hook with storage blocked.

### I3. A dropped build connection is reported as "The build failed", and the stored dossier is never offered

- **Where:**
  - `src/lib/sse.ts:66-81`: `reader.read()` and `JSON.parse` are not guarded;
  - `src/components/research/BuildProgress.tsx:33-36`: any non-`BuildError` becomes "The build failed";
  - `src/components/dossier/DossierScreen.tsx:16`: `useDossier` is disabled while building.
- **Scenario:**
  - A phone loses signal mid-build, or the function is killed with the body unterminated. The browser rejects `reader.read()` with `TypeError: network error`, and the user sees "The build failed" with no hint. The Node probe showed the rejection is `TypeError`, not a `BuildError`.
  - A malformed `data:` frame rejects with a `SyntaxError`, with the same result.
  - Review Focus 4 asks for "The build stopped before finishing" and a link to the stored dossier if one exists. The link is not implemented on any path.
  - "Try again" then starts a second server-side build while the first worker may still be running and saving.
- **Fix:**
  - In `sse.ts`, wrap `reader.read()` in try/catch and throw `BuildError("incomplete", STOPPED)` unless `signal.aborted`. Wrap `JSON.parse` and skip a bad frame (or treat it as an error).
  - In `BuildProgress`, on `incomplete`, fetch `/research/{sym}` and, if it exists, show "Open the saved dossier" next to "Try again".

### I4. When the snapshot is older than 7 days, Today is a dead end

- **Where:** `src/components/today/StaleNotice.tsx:4-7,21-22`.
- **Scenario:**
  - The newest filing is 10 days old. This happens if the Plan 5 cron fails or stops, or if graders open the app well after the deadline.
  - At 24 h, the notice offers "Show 3 days" and "Show 7 days". Both lead to the same empty notice, because neither window can reach `latest_filing_at`.
  - At 7 days, no button is offered at all. The user has to discover Custom and type two dates.
- **Fix:**
  - Compute the age of `latest_filing_at` and offer only the presets that reach it.
  - When none do, offer a range that ends at the newest filing, e.g. "Show the week up to 7 Nov" = `{kind: "range", start: latest − 7 d, end: latest}`.

### I5. Filing-alert links land on nothing when the alert window and Today's 7-day window differ

- **Where:** `src/components/alerts/AlertLog.tsx:37-44`; `src/app/page.tsx:47-51`.
- **Scenario:**
  - `/alerts` anchors its 7 days at the newest data point (`_alert_anchor`). The link writes `hours: 168`, which ends at the current time.
  - On a Monday morning, with the newest filing from Friday evening, every alert from the first ~2.5 days of the alert log points at a story outside Today's window. If the user's floor is Critical, an Important story sits in the routine drawer, which has no `id`.
  - Tapping such an alert opens Today at the top, with nothing scrolled to and nothing explained. The fixtures pin the clock, so the e2e test cannot see this.
  - The plan's fallback (`/filings/{seq_id}` with `subscribed`) was not built.
- **Fix:**
  - Write the alert response's own window: `{kind: "range", start: data.window.start, end: data.window.end}`.
  - On Today, when the hash target is not among `stories`, open the routine drawer if the story is there, or else show a line such as "That story is outside this window".

## Minor

### M1. `?build=1` skips the stored-dossier check

- **Where:** `DossierScreen.tsx:14-16`; `SearchBox.tsx:64`.
- **Scenario:**
  - The research list is still loading on a cold start, or it failed, so `known` is empty. The user picks a company that already has a dossier, sees "Build a dossier", and a full rebuild starts (the backend's cache only lasts 10 min).
  - After Cancel or a failure, the URL keeps `?build=1`, so a reload starts another build.
- **Fix:** when `build=1`, check `useDossier` first. Use `router.replace` to drop `?build=1` once the build starts or is cancelled.

### M2. Focus revalidation has side effects on Today

- **Where:** `src/app/page.tsx:47-51,64-69`.
- **Scenario:**
  - The hash scroll effect depends on `[data]`, and every digest has a new `window.end`. A user who arrived from an alert, scrolled on, switched apps and came back is jumped back to the alert's story.
  - The "Updating" line is inserted above the feed on every revalidation, which shifts the layout.
  - A malformed hash (`/#story-%E0`) throws a `URIError` inside the effect and takes down the page.
- **Fix:** scroll once per hash, then clear it with `history.replaceState`. Wrap the decode in try/catch. Reserve the space for the "Updating" line, or show it in the header.

### M3. Times older than 24 h read "3 d ago" instead of "6 Nov, 18:40"

- **Where:** `StoryCard.tsx:64`, `RoutineDrawer.tsx:47`.
- **Scenario:** on a 7-day window, card times read "4 d ago" instead of the date and time the Global Constraints ask for. `format.when()` already exists and is unused.
- **Fix:** use `when()`.

### M4. Several tap targets are under 44 px

- **Where:**
  - `CitationChip` `min-h-8` (32 px; `CitationChip.tsx:20`), the most-tapped control in the dossier;
  - `Segmented` `min-h-10` (40 px; `States.tsx:52`) for the window and floor;
  - the Holdings symbol link (`Holdings.tsx:24`, one text line);
  - the routine drawer's subject links (`RoutineDrawer.tsx:40`);
  - the member "PDF" links (`StoryCard.tsx:100-102`).
- **Fix:** `min-h-11` or a padded hit area.

### M5. The build screen's live region announces the elapsed counter every second

- **Where:** `BuildProgress.tsx:53-56`. The whole section is `aria-live="polite"`, and it contains the "N s so far" text, which changes every second for 40–90 s.
- **Fix:** put `aria-live` on the progress list only. Leave the timer outside it, or update the timer's text every 10 s.

### M6. Smaller a11y nits

- `aria-label` on a plain `<span>` (the computed-line † in `ResultsGrid.tsx:33`) is ignored by most screen readers; use sr-only text.
- `Segmented` uses `role="radio"` without arrow-key handling or roving tabindex.
- "Mark seen" changes both its label and `aria-pressed`; keep one label.
- The toast `<p role="status">` (`alerts/page.tsx:69`) is mounted together with its text, so it may not be announced; keep the region mounted.
- The `MiniBars`/`MiniLine` readouts are `aria-live` and announce every hover.
- `scrollIntoView({behavior: "smooth"})` in `page.tsx:42` ignores `prefers-reduced-motion`.

### M7. Seen cards flash in rank order and then jump to the bottom on each load

- **Where:** `StoryList.tsx:11`.
- **Cause:** `StoryList` reads `seen` through its own `useStored`, which returns `[]` until its effect runs after the first paint.
- **Fix:** read `seen` on the page with the other settings and gate on `ready`.

### M8. Service worker details

- **Where:** `public/sw.js`.
- Fallback happens only on a network error. A Vercel 502 or 504, a cold start past 15 s, or an API that is down shows the error, not the saved copy, even though a copy exists.
- `VERSION` is a constant, so:
  - the static cache is never pruned across deploys;
  - cache-first `/icons/*` (not content-hashed) never refreshes.
- The data cache is unbounded, with one entry per search term, custom range and rules body.
- `isApiRead` matches paths from the origin root. An API URL with a path prefix (`https://host/api`) silently disables offline data.
- The banner says "Offline" when the device is online but the server is down.
- I found no way for it to cache the SSE stream, an error response, or a POST under the wrong body, and navigation stays network-first.

### M9. The source sheet misses some highlights the backend verified

- **Where:** `SourceSheet.tsx:10-53`.
- **Cause:** the backend matches quotes after NFKC and also across page breaks, citing the first page of the pair (`cite.py:57-73`, `grounding.py normalize`). `fold()` does no NFKC, so ligatures such as ﬁ and ﬂ (common in annual-report PDFs) break the match, and a quote that straddles a page cannot match a single page.
- **Effect:** the sheet falls back to the page with no highlight, as the plan allows. All 7 captured pages do highlight.
- **Fix:** apply NFKC per character in `fold`. For a quote that straddles pages, highlight the longest matching prefix.

### M10. `/research/%E0%A4%A` returns a 500

- **Where:** `src/app/research/[symbol]/page.tsx:9`.
- **Cause:** `decodeURIComponent` throws. Next passes the raw segment here: `/research/ABC%25` returns 200, so the decode itself is needed.
- **Fix:** wrap it in try/catch and call `notFound()`.

### M11. The request timeout covers only the headers

- **Where:** `src/lib/api.ts:22-32`.
- **Cause:** the timer is cleared once `fetch` resolves, so a body that stalls in `res.json()` (a slow mobile network on the 187 KB 7-day digest) leaves the skeleton up indefinitely.
- **Fix:** clear the timer after the body has been read.

### M12. The build error copy is the raw server string

- **Where:** `BuildProgress.tsx:68`.
- **Scenario:** the user sees "build timed out" and "build failed: RuntimeError": lowercase, with no next step. After a timeout, the worker may still finish and save.
- **Fix:** map the known details, e.g. "The build ran out of time. FINN may still save it; try again in a minute."

### M13. Unruled plan deviations and copy

- The pencil stroke runs 900 ms after a 250 ms delay, where the plan says 400 ms (`globals.css:125`).
- Sheets have a 14 px radius, where the plan says 8 px (`globals.css:135`).
- The members toggle reads "4 filings", where the plan says "4 filings in this story".
- Holdings show the volume ratio only when it is over the limit, and not in bold. The plan asks for it on every row, in bold at or above the multiple.
- "1 promises tracked" (`DossierList.tsx:18`); use `plural`.

## Rulings in the ledger

- **P4-R1 to P4-R4:** sound. R4 is verified in the browser.
- **Task 0** (commit grouping) and **Task 3** (NBFC fixture for the bank test, the check circle for Mark seen, deltas in ink, `cleanSubject`, the stub route): sound.
  - The bank-format results layout has no UI test. Acceptable, because `ResultsGrid` renders whatever rows the card carries.
- **Task 4** (newest 8, category from `story_id`, "N sessions back"): sound.
- **Task 5** (the build lives on the dossier route behind `?build=1`): the right call. It has two side effects the ruling missed:
  - `useDossier` is disabled while building, which is why the Focus 4 "link the stored dossier" path is absent (I3);
  - `?build=1` bypasses the stored dossier (M1).
- **Task 6:**
  - Track record before Open promises: an acceptable product call, and DESIGN.md records it. Note that in 4 of 7 seed dossiers every row is pending, so the stated reason ("the verdicts are the point") does not hold there. Harmless.
  - The month on twin-quarter chips and the reflow: sound.
- **Task 7:**
  - Caching POST digest and alerts under a body key: sound. The cache is unbounded (M8).
  - Service worker opt-in in Playwright, and axe in dark mode: sound.
- **None is wrong.**

## Declined to judge

- The backend keeps building after the client cancels or disconnects, which wastes LLM cost. This is backend behaviour, outside Plan 4.
- Whether live builds should be durable on Vercel. That is Plan 5's call. I judged only the frontend's reaction to a missing dossier (C1).
- The visual quality of the committed screenshots. I did not open the PNGs.
- iOS Safari specifics: `<dialog>` focus return, standalone service-worker behaviour and safe-area rendering. These need a device.
- Dev-only StrictMode double effects, such as two build requests under `next dev`.
- Exact WCAG contrast numbers beyond what axe checks.

## Verdict

**Ready to merge with fixes.** Fix C1 and I1 to I5 before merge. Each is contained, at most tens of lines plus a test. The minor items can follow.

C1 breaks the live-build demo on the deployment Plan 5 describes. I1 to I3 are Review Focus items 2 to 4 that pass their happy-path tests but fail in the probes above. Everything else, including empty windows, partial dossiers, M&M encoding, provenance typography and the service worker, holds up.
