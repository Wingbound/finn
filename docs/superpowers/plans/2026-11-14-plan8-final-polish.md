# FINN Plan 8: final audit, fixes, spoken brief, submission (14 Nov 2026)

## Context

The submission is due **15 Nov 2026**. The user asked for four things:
1. Re-check every deliverable in the brief.
2. Bug-check the whole codebase.
3. Add anything missed.
4. Prepare and commit the final submission.

They chose **fixes plus a spoken brief** ("Listen") and **no phone notifications**. The original design plan that used to be in this file lives on as `finn/docs/DESIGN.md`.

### Audit: every required deliverable is shipped

| Brief requirement | Status | Evidence |
|---|---|---|
| Mobile-first prototype, deployed link | ✅ | https://finn-qx98.vercel.app; the user tested it on their phone |
| GitHub repo | ✅ | github.com/Wingbound/finn (public) |
| AI build history | ✅ (to refresh) | `ai-history/` holds the plan ledgers and the redacted session as of 11 Nov |
| Covering-email writeup (what was built, decisions, what was left out, next steps) | ✅ | `docs/COVER_EMAIL.md`; filled copy in `ENAM/cover-email-final.txt` |
| 15–20 holdings | ✅ | 18 holdings in `backend/finn/portfolio.yaml` |
| 3–5 research companies | ✅ | 5 outside the portfolio: DIXON, HDFCBANK, IDEA, INDIGO, POLYCAB |
| Generalises to any NSE ticker | ✅ | live build over SSE; re-verified below |
| Data: EOD prices, filings, ARs and transcripts | ✅ | NSE MCP (Yahoo as fallback), NSE announcements, screener |
| Push: digest window (24h default, chooser), prioritised, routine collapsed | ✅ | 24h / 3d / 7d / custom; floor control; routine drawer |
| Push: configurable alerts (categories, volume ×, price %) | ✅ | `RulesSheet.tsx`, `POST /alerts` |
| Management change → bio | ✅ (filing profile) | `finn/enrich/people.py`. A web bio isn't possible on the free tiers (see below) |
| Results → Revenue, EBITDA, PBT and PAT, QoQ and YoY | ✅ | XBRL, `ResultsGrid.tsx` |
| Other types: one-liner or priority | ✅ | `finn/enrich/brief.py`, 7 categories |
| Pull menu, plus the promised-vs-delivered worked example | ✅ | Promise Ledger, snapshot, trajectory, balance sheet and cash, bull/bear |
| Primary sources only | ✅ | grounding checks and citations |
| Model routing, caching and cost | ✅ | `finn/llm/router.py`, `docs/EVALS.md` |
| Try other interaction models | ⚠️ | finite feed only → **adding "Listen"** (Task 5) |

**Checked 14 Nov: no web bios.** A Gemini call with Google Search grounding returns 429, though plain calls work, so grounding has no free quota. Groq lists no web-search ("compound") models for this key. The card keeps the profile filed under SEBI's rules, and the email says why.

### What the bug check found (live probes plus three code passes)

**High** (a grader would see these):
- **"Nothing matters yet" on a 24-hour window.** The refresh is scheduled once a day, and GitHub starts the "06:00" cron around 12:30 IST, so the 24-hour window is mostly empty. Today's live screen says "Nothing matters yet".
- **Wrong company on M&M's card.** M&M's results card leads with a *Tech Mahindra* promise (`finn/research/link.py` has no filter for other companies).
- **Paid rebuilds of saved dossiers.** A search tap made before the dossier list loads, or a reload after Cancel (`?build=1`), rebuilds a stored dossier. That build runs for about 80 s, costs LLM calls, and can change the hand-audited verdicts. The server reuses only dossiers under 10 minutes old (`main.py:263,449-452`).

**Medium:**
- The price "as of" is the fetch time, not the session date (`Holdings.tsx:8-12`).
- Tapping a filing alert saves that week as Today's window permanently (`AlertLog.tsx:40`).
- The "What management said" quote is cut to 3 lines with no "Show more" (`PromisePanel.tsx:43-48`).
- The "Updating" line shifts the layout (`page.tsx:94-98`).
- Search lists BSE-only numeric codes such as "543927", which can't build.
- `people.py:125` never falls back to the NSE summary when the PDF text is empty, and it runs on noise filings too.
- One failure in `refresh.py:150-170` skips both enrichment stages.
- The live build has no client-side timeout (`sse.ts:62`).
- The refresh commits every run, even when nothing changed, which redeploys and wipes live builds. It also pushes without a rebase first.

**Low:**
- `nse_mcp.py:172` uses a naive `today`.
- With `lookback` set to 5–9, volume alerts never fire (`models.py:132` against `alerts.py:9`).
- A noise-only window counts as empty (`page.tsx:68`).
- The Custom sheet ignores the current range.
- The toast timer isn't cleared.
- Heading levels skip.
- Docs are stale: the README's refresh step and DESIGN.md's references to Hugging Face.

## How it runs

- **Method:** inline (superpowers:executing-plans), test-first, on branch `feat/final-polish`, with one commit per task.
- **Plan in the repo:** first, save this plan as `finn/docs/superpowers/plans/2026-11-14-plan8-final-polish.md`.
- **Review:** after the last task, a fresh final reviewer on the most capable model reads the whole branch, followed by one fix pass. Then merge to `main`, which deploys.
- **Rules from CLAUDE.md:**
  - no secrets and no personal details in the repo;
  - arithmetic stays in Python;
  - verdict guards only downgrade.

### Task 1: a digest that isn't empty on a quiet day, plus fresher data

- **Quiet-window notice.** When the chosen window has no stories at the current floor, Today shows a teaser built from a 7-day digest: "Quiet 24 hours. The last 7 days: N things matter. [Show 7 days]".
  - Extend `frontend/src/components/today/StaleNotice.tsx` and fetch with the existing digest hook (`src/lib/hooks.ts`).
  - Fetch the second digest only when the first one is quiet.
  - Fix the case where a noise-only window counts as empty (`src/app/page.tsx:68`).
- **More refreshes.** In `.github/workflows/refresh.yml`, run on weekdays at `17 1,4,7,10,13,16 * * 1-5` (06:47 to 21:47 IST) and on weekends at `17 4 * * 0,6`. Odd minutes avoid the top-of-hour queue.
- **Workflow fixes:**
  - `git pull --rebase` before pushing.
  - Commit only when the data changed. Add `backend/scripts/seed_changed.py BEFORE AFTER`, which hashes the content tables in key order (filings, prices, enrichments, results, dossiers) and ignores meta timestamps. It exits 0 when they changed and 1 when they didn't. Test it with pytest on tmp DBs.
- **Tests:** vitest for the quiet teaser (shown when quiet, hidden otherwise, button switches the window); pytest for `seed_changed`.

### Task 2: never rebuild a saved dossier by accident

- **Backend.** `GET /research/{symbol}/build` streams a stored dossier of any age straight back as `done`, with no LLM calls (`backend/finn/api/main.py:446-470`).
- **Search filter.** `/research/search` drops hits whose symbol is all digits, i.e. BSE-only (`main.py:291`).
- **Frontend:**
  - After Cancel or done, `router.replace` drops `?build=1` (`src/components/dossier/DossierScreen.tsx:74`).
  - Add a 300 s client timeout in `src/lib/sse.ts` that ends in the existing error state with "Check for a saved copy".
- **Tests:** pytest (a stored dossier gives an immediate `done` and the router is never called; numeric symbols are filtered out); vitest (the URL is cleaned after cancel; timeout gives the error state).

### Task 3: correct results cards and alerts

- **Promises about other companies.** `backend/finn/research/link.py` skips a promise whose quote names *another* known company. Known names come from the portfolio and the stored dossiers, using each name without "Ltd/Limited", minus the reporting company's own names. Pytest: the M&M / "Tech Mahindra" row is excluded, and M&M's own promises stay. The dossier ledger keeps the row.
- **Price date.**
  - The caption reads "Prices: NSE end-of-day, close of 12 Nov." using the newest row `date` (`src/components/alerts/Holdings.tsx` `priceCaption`, `src/app/alerts/page.tsx:67`).
  - Update the vitest.
- **Alert links.** A filing alert opens `/?from=…&to=…#story-<id>` and the window is used once, never saved (`src/components/alerts/AlertLog.tsx:40`, `src/app/page.tsx`). Update `tests/alerts.test.tsx`.
- **Promise quote.** `PromisePanel.tsx` gets "Show more" for clamped quotes and the right heading level.
- **No layout shift.** The "Updating" status gets a fixed-height slot (`page.tsx:94-98`).

### Task 4: refresh robustness (backend)

- **People enrichment** (`finn/enrich/people.py:123-127`): fall back to `nse_summary` when the PDF text is empty, and skip noise filings, the same way `brief.py:176-180` does.
- **Separate stages** (`scripts/refresh.py:150-170`): give people, briefs and financials their own `try` blocks so one failure doesn't skip the others.
- **IST date** (`finn/ingest/nse_mcp.py:172`): `today` is the IST date (`ZoneInfo("Asia/Kolkata")`).
- **Lookback floor** (`finn/models.py:132`): `Rules.lookback` has a minimum of 10, to match `MIN_VOLUME_HISTORY`.
- **Tests:** a pytest for each fix.

### Task 5: spoken brief ("Listen")

- **`frontend/src/lib/briefScript.ts`.** A pure function, `briefScript(digest): string[]`, that writes about 60 seconds of plain sentences:
  - the count ("Three things matter in the last 24 hours.");
  - one sentence per story: company, a plain category label, then the one-liner, the results headline ("Revenue up 12% year on year"), or the people change;
  - "N routine filings set aside. You're caught up."
  - Numbers come from the digest. Nothing is computed beyond picking fields.
- **`frontend/src/components/today/ListenButton.tsx`:**
  - uses `speechSynthesis` with `SpeechSynthesisUtterance` and prefers an `en-IN` voice;
  - Play/Stop toggle with `aria-pressed`;
  - hidden when the browser can't speak;
  - stops when it unmounts or the tab is hidden.
  - It sits in the Today header.
- **Vitest:** the script (plurals, the empty day, results wording, people wording); the button with a mocked `speechSynthesis` (speaks the lines, stop cancels, hidden when unsupported).

### Task 6: bug check and verification

- **Local runs:**
  - backend: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`;
  - frontend: `npm run test`, `npm run typecheck`, `npm run lint`, `npm run build`, `npm run e2e`.
- **Final review:** a fresh reviewer on the most capable model reads the whole-branch diff, followed by one fix pass. Then merge to `main` and push (Vercel deploys).
- **Live checks after the deploy:**
  - Playwright MCP at 390×844 on https://finn-qx98.vercel.app:
    - Today: the quiet teaser; the 7-day view with a results card and a people card; Listen.
    - Alerts: the caption shows the session date; a rules change produces an alert.
    - Research: a stored dossier opens without a build; the citation sheet opens.
    - One live build of an NSE ticker that isn't in the seed (e.g. ASIANPAINT, about $0.05), to check that it generalises.
    - The console has no errors.
  - Then `LIVE_URL=… LIVE_API=… npx playwright test -c playwright.live.config.ts`.
  - Trigger `gh workflow run refresh.yml` once to check the change check and the rebase.

### Task 7: final submission prep

- **Docs:**
  - README: test counts, eight plans, refresh cadence, and the local refresh including `compact_seed.py`.
  - `docs/EVALS.md` §5: the Plan 8 checks.
  - `CLAUDE.md`: status.
  - `docs/PROJECT_BRIEF.md`: tick the submission checklist.
  - `docs/DESIGN.md`: fix the stale hosting lines.
- **`docs/COVER_EMAIL.md`:**
  - mention "Listen";
  - under "What I left out", add the web bio: the free tiers have no web search, so the card quotes the profile the company filed under SEBI's rules;
  - re-run the humanizer pass on the changed lines.
- **History and merge:** archive the ledger to `ai-history/plan8-inline/`, then merge and push.
- **Filled email:** regenerate `ENAM/cover-email-final.txt` (outside the repo, mode 600) from `COVER_EMAIL.md` with the user's details.
- **History export, last of all:**
  1. Run `FINN_REDACT_FILE=ENAM/.finn-redact.txt uv run python scripts/export_history.py <session>.jsonl --out <scratch>`.
  2. Run `python3 -I ENAM/.finn-scrub.py <file>`.
  3. Scan for the redaction list, entry-number pattern, phone, gmail, `/home/`, key patterns and the markers from other applications. Every scan must come back at 0.
  4. Copy the result to `ai-history/claude-code-session.md`, commit and push.
  5. Confirm on GitHub.
- **Hand-off:** the user sends the email.

## Not doing

- **Web Push notifications:** the user chose not to.
- **Web bios:** no free web search is available (checked above).
- **Chat Q&A.**
- **Low-severity items** stay listed in EVALS "Known limits":
  - the SSE id match;
  - the NFKC normalisation of ligatures in citations;
  - versioning of the service-worker cache;
  - accessibility of the segmented control;
  - the 2% tolerance in pace notes.

## Verification (end to end)

1. All local suites and the build pass (Task 6), with the numbers recorded in EVALS.
2. On the live phone viewport: the quiet-day teaser appears on 24h, M&M's results card no longer shows Tech Mahindra, the price caption names the session date, Listen speaks, a stored dossier opens instantly, and a new ticker builds live.
3. A manual refresh run either commits only because data changed, or says "No change".
4. GitHub `main` has CLAUDE.md, COVER_EMAIL.md, Plan 8 and the fresh session export. Every leak scan comes back at 0.
