# FINN Plan 4: Frontend (mobile-first PWA)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A phone-first installable web app with three tabs over the existing FastAPI backend:
- **Today**: a digest that ends;
- **Alerts**: holdings, alert log and rules;
- **Research**: a dossier led by the Promise Ledger.

All user state stays on the device.

**Architecture:**
- A Next.js App Router app in `frontend/`. Every screen is a client component that fetches from `NEXT_PUBLIC_API_URL`.
- Rules, the noise floor, the window and seen marks live in `localStorage` and go out with each request. The server stays stateless (DESIGN §7b).
- There is no component library and no chart library. Charts are small hand-built SVGs that follow the dataviz skill.
- Tests run against fixtures captured from the real backend:
  - Vitest for library logic and components;
  - Playwright at 390×844 with the API mocked from the same fixtures.

**Tech Stack:** Node 22, npm, Next.js 16.4.5, React 19.3.1, TypeScript 5.9.3, Tailwind CSS 4.3.5 (`@tailwindcss/postcss`), SWR 2.5.1, Vitest 5.1.0 + Testing Library 16.3.3 + jsdom, and Playwright 1.65.0. Fonts are IBM Plex Sans and Literata via `next/font/google`, self-hosted at build time.

**Spec:**
- `docs/DESIGN.md` §1 "Surfaces" (Today, Alerts & Portfolio, Research) and §7b (user state on the device);
- the Plan 3 notes in `.superpowers/sdd/2026-11-09-plan3-pull-research/progress.md`, restated under Global Constraints below.

## Design system (decided; every task follows it)

**Point of view.** FINN is the editor, and the blue pencil marks its editorial acts. On Today it strikes through the routine filings it set aside. Everywhere else it is the interactive accent. Typography shows provenance:
- **Literata** (serif) is used only for text quoted verbatim from a document: management's words, filing text and evidence;
- **IBM Plex Sans** is used for filed numbers and for FINN's own words.

A one-line key in the dossier says so.

**Color tokens** (CSS variables on `:root`, redefined under `prefers-color-scheme: dark`):

| token | light | dark | job |
|---|---|---|---|
| `--ink` | #1A1D24 | #E8EAEE | primary text |
| `--ink-2` | #545B66 | #A3AAB5 | secondary text |
| `--paper` | #FFFFFF | #14161B | page |
| `--well` | #F2F4F7 | #1D2026 | insets, drawers, sheets |
| `--rule` | #DDE1E6 | #2C3038 | hairlines |
| `--pencil` | #2346C6 | #8DA2FF | accent: strike, links, active tab, focus ring |
| `--kept` | #1E7A4C | #2B9A72 | kept / price up |
| `--partly` | #B98310 | #B58C14 | partly |
| `--missed` | #B3261E | #EC4F72 | missed / price down |
| `--pending` | #6B7280 | #9AA1AC | pending, not mentioned again |

Validated 2026-11-09 with the dataviz `validate_palette.js`, with kept, partly and missed adjacent. Light on #FFFFFF passes every check (worst protan ΔE 10.0). Dark on #14161B passes with one CVD warning: deutan ΔE 7.8 between missed and partly. That is allowed only with secondary encoding, and every status has it: glyph and word, plus 2px gaps in the tally. Pending is deliberately grey. Status marks are coloured; status words stay in `--ink`.

**Type scale** (px, mobile): 13 caption · 15 body (Plex 400, line-height 1.45) · 16 quote (Literata 400, line-height 1.55) · 17 card title (Plex 600) · 21 section (Plex 600) · 40 Today headline (Plex 600, tracking −0.01em). Numbers use `font-variant-numeric: tabular-nums` everywhere.

**Layout.**
- One column, max-width 560px centred, 16px gutters, text left-aligned and numbers right-aligned in grids.
- A fixed bottom tab bar (Today, Alerts, Research) with `env(safe-area-inset-bottom)`, 44px minimum targets.
- Stories are separated by spacing plus one hairline. There are no shadows. A radius (8px) appears only on interactive chips, inputs and bottom sheets.

**The one bold moment.** The Today header reads "4 things matter" at 40px. Below it is "37 routine filings", struck through by a blue-pencil SVG stroke that draws once on load (400 ms; static under `prefers-reduced-motion`). Tapping it opens the routine drawer. Nothing else animates on its own.

**Do not use** (these are the generic tells):
- all-caps labels or eyebrows;
- middle-dot meta strings;
- "→" on buttons;
- monospace data labels;
- identical shadowed cards;
- gradient washes;
- a single accented word in a headline.

Copy is in sentence case, uses plain verbs, and names things from the user's side. Errors say what happened and what to do.

## Global Constraints

- **Frontend location.** All frontend code lives in `frontend/`. The backend changes only in Task 0 (the fixture export script).
- **Pinned versions.** Use the exact versions in Tech Stack (`--save-exact`). No other runtime dependencies without a ledger ruling.
- **API base.** `process.env.NEXT_PUBLIC_API_URL`, default `http://localhost:8000`, with no trailing slash.
- **Device storage.** Keys are `finn:v1:rules`, `finn:v1:floor`, `finn:v1:window`, `finn:v1:seen`. Every read and write is wrapped in try/catch. Corrupt or missing values fall back to defaults, and the app works with storage blocked.
- **Times.** Shown in IST (`Asia/Kolkata`). Relative within 24 h ("2 h ago"), otherwise "9 Nov, 14:05".
- **Money.** Shown as ₹ crore with Indian digit grouping (`₹1,23,456 cr`). Percentages carry a sign (+4.1%, −2.0%). Margins move in bps (+120 bps).
- **Plan 3 product rules:**
  - always pass the digest's `subscribed` to `/filings/{seq_id}`;
  - when the window is empty, use `latest_filing_at` to say how old the newest filing is and offer a wider window;
  - split the ledger into "Open promises (latest call)" and "Track record (earlier calls)";
  - show status `dropped` as "Not mentioned again";
  - never present FACTS numbers as quoted: a FACTS citation chip reads "Computed from filed financials" and is not set in Literata;
  - a dossier whose `cost.usd_list_price` is 0 shows "Served from cache" instead of a price;
  - show credibility only when `ledger.credibility_pct` is not null.
- **Status is never color alone.** Every status carries a glyph and a word: ✓ Kept · ◐ Partly · ✕ Missed · ○ Pending · – Not mentioned again.
- **Quality floor:**
  - no horizontal scroll from 360 to 430 px;
  - a visible `:focus-visible` ring (2px `--pencil`);
  - `prefers-reduced-motion` respected;
  - WCAG AA contrast;
  - no console errors on any screen.
- **Commands.** `npm run test` (vitest), `npm run e2e` (playwright), `npm run lint` (eslint) and `npm run build` must pass before each commit. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Empty or stale window.** The seed is days old, or it is Monday morning, so the 24 h digest has no stories. Today shows "Nothing new in the last 24 hours. Newest filing: 6 Nov, 18:40", with buttons for 3 days and 7 days, not a blank page. (Task 3)
2. **API cold start or unreachable.** A Vercel cold start takes several seconds, or the API is down. Each screen shows a skeleton, then after 15 s or on error "Couldn't reach FINN's server", with a Retry button. Stale SWR data stays visible. (Task 2 client, Tasks 3–6 screens)
3. **Device storage blocked or corrupt** (a private window, or `finn:v1:rules` = `"{bad"`). Defaults apply silently, and saving rules still works for the session. (Task 2)
4. **Live build edge cases:**
   - an `error` event (the ticker is not on screener, the build failed or timed out) shows the server's `detail` and a "Try again" button;
   - a dropped connection with no `done` shows "The build stopped before finishing" and links the stored dossier if one exists;
   - a buffered, non-streaming proxy still works, because all events arrive at once.

   (Task 5)
5. **Partial dossiers.** `ledger`, `snapshot`, `trajectory` or `health` may be null. A lender has `trajectory.lender` set, a different margin label and no CFO/PAT. In each case the section shows the matching `notes` line ("Ledger skipped: …") and never crashes or renders NaN. (Task 6)

---

### Task 0: Fixture export (backend) and TypeScript types

**Files:**
- Create: `backend/scripts/export_fixtures.py`
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/tests/fixtures/*.json` (generated)

**Interfaces:**
- **`export_fixtures.py --db PATH --out DIR`** calls the FastAPI app through `TestClient` against a copy of PATH and writes:
  - `health.json`, `portfolio.json`, `alerts.json` (default `Rules()`);
  - `digest-24h.json`, `digest-7d.json` and `digest-empty.json` (a window before any filing);
  - `results-<SYM>.json` for one non-financial and one bank;
  - `filing-<seq>.json`;
  - `research-list.json`;
  - `dossier-<SYM>.json` for every stored dossier;
  - `source-<SYM>-<id>-<page>.json` for one citation per dossier;
  - `build-<SYM>.sse`, the raw SSE text of a cached build.

  It pins `get_now` to the newest filing time + 2 h, so fixtures are deterministic.
- **`types.ts`** mirrors `backend/finn/models.py` and the dict-shaped routes: `Category`, `Tier`, `Filing`, `ScoredFiling`, `Story`, `ResultsCard`, `PersonChange`, `Brief`, `Rules`, `SymbolOverride`, `Alert`, `Digest`, `PortfolioRow`, `Portfolio`, `AlertsResponse`, `Dossier`, `LedgerRow`, `Promise`, `Citation`, `Source`, `Trajectory`, `BalanceSheetHealth`, `Flag`, `Point`, `ResearchListItem`, `SearchHit`, `BuildEvent`.

- [ ] Write the export script. Run it against `backend/seed/finn.sqlite`. Check that the files exist and that `digest-24h.json` has at least one story.
- [ ] Write `types.ts`, plus a vitest `types.test.ts` that loads every fixture and asserts the presence and types of each field the UI reads. This is a field-by-field runtime check, so a backend shape change fails a test.
- [ ] Commit.

### Task 1: Scaffold, tokens, shell

**Files:**
- `frontend/package.json`, `next.config.ts`, `tsconfig.json`, `postcss.config.mjs`, `eslint.config.mjs`, `vitest.config.ts`, `playwright.config.ts`;
- `src/app/layout.tsx`, `src/app/globals.css`, `src/app/manifest.ts`;
- `src/components/TabBar.tsx`;
- `public/icons/*`.

- [ ] **Scaffold.** Set up by hand, not with `create-next-app` (pinned versions, no template cruft). Use the `src/` layout and Tailwind v4 with `@theme` mapping the tokens above.
- [x] **Validate the palette.** Done; see Design system.
- [ ] **Layout.** Fonts through `next/font/google` (Plex Sans 400/500/600, Literata 400/400-italic), exposed as `--font-sans` and `--font-quote`. Tab bar routes: `/` Today, `/alerts`, `/research`. The active tab is marked by `--pencil` plus `aria-current="page"`.
- [ ] **Manifest.** `name` FINN, `display` standalone, `theme_color` = `--paper`, and 192/512 maskable icons. The icon is a blue-pencil "F" stroke drawn as SVG, then rendered to PNG.
- [ ] **Tests.**
  - Vitest: `TabBar` marks the current route.
  - Playwright smoke test at 390×844: each tab loads with no console errors and no horizontal overflow (`document.documentElement.scrollWidth <= innerWidth`).
- [ ] Commit.

### Task 2: Client library: API, device store, formatters

**Files:** `src/lib/api.ts`, `src/lib/store.ts`, `src/lib/format.ts`, `src/lib/sse.ts`, and their tests.

**Interfaces:**
- **`api.ts`:**
  - `apiGet<T>(path)` and `apiPost<T>(path, body)`. They time out at 15 s and throw `ApiError {status, detail}`; the message is "Couldn't reach FINN's server" on network failure or timeout, or the server's `detail` otherwise.
  - SWR hooks: `useDigest(params)`, `usePortfolio()`, `useAlerts(rules)`, `useResults(sym)`, `useResearchList()`, `useDossier(sym)`, `useSource(sym, id, page)`.
- **`store.ts`:**
  - `readStore<T>(key, fallback, validate)` and `writeStore(key, value)`, plus `useStored<T>(key, fallback, validate)`. It is SSR-safe: it returns the fallback until mounted.
  - `DEFAULT_RULES` equals the backend `Rules()` defaults. `validateRules` clamps values to the backend's bounds.
  - `seen` is a set of story ids, capped at 500 (FIFO).
- **`format.ts`:**
  - `crore(n)` gives `₹1,23,456 cr`; null gives `–`.
  - `pct(n)` is signed with 1 decimal place; `bps(n)` is signed.
  - `when(iso, now)` follows the IST rules above.
  - `ago(iso, now)`.
  - `categoryLabel(c)`: plain names, e.g. `mna` → "Deal", `management_change` → "People", `fund_raise` → "Fund-raise".
  - `statusLabel(s)` gives the glyph and word.
- **`sse.ts`:** `buildDossier(sym, {onProgress, signal}) → Promise<{dossier, excerpts}>`. It is built on `fetch` + `ReadableStream` parsing, not `EventSource`, so it can be aborted and so a buffered response still parses. It rejects with `BuildError {kind: "error"|"incomplete", detail}`.

**Tests:**
- `format.test.ts`:
  - Indian grouping: 123456.7 → `₹1,23,457 cr`; 999 → `₹999 cr`; negatives keep their sign;
  - IST rendering across the UTC date boundary.
- `store.test.ts`: corrupt JSON gives the default; a throwing `localStorage` gives the default and a no-op write; out-of-range rules are clamped.
- `sse.test.ts`:
  - parses the `build-<SYM>.sse` fixture into progress messages plus a `done` payload;
  - pings are ignored;
  - an `error` event rejects with its detail;
  - a stream that ends without `done` rejects with `incomplete`.
- `api.test.ts`: a timeout gives an `ApiError` with the unreachable message (fake timers).

- [ ] Write the tests, then implement, then run them.
- [ ] Commit.

### Task 3: Today

**Files:**
- `src/app/page.tsx`;
- `src/components/today/{Header,WindowPicker,FloorControl,StoryCard,ResultsGrid,PeopleList,BriefBlock,RoutineDrawer,CaughtUp,StaleNotice}.tsx`;
- `src/components/PencilStrike.tsx`.

**Behaviour:**
- **The request.** `POST /digest` with `{hours | start,end, floor, subscribed: rules.categories}` from the store.
- **Window picker.** Options are 24 h, 3 days, 7 days and Custom. Custom opens a sheet with two `datetime-local` inputs, IST.
- **Floor control.** Three segments: Critical, Important, Everything.
- **Header.** "{counts.shown} things matter" (1 → "1 thing matters"; 0 → "Nothing matters yet"). The routine count is struck by `PencilStrike`, and tapping it scrolls to and opens `RoutineDrawer`. When `counts.hidden` > 0, a quiet line follows: "{n} pieces of noise dropped".
- **`StoryCard`,** by `category`:
  - **First line:** symbol in bold and the company name, with `ago(latest_at)` on the right.
  - **Results:** `ResultsGrid` shows Revenue / EBITDA / PBT / PAT (or the bank and NBFC rows as given) as value, QoQ and YoY columns. Margin rows show bps. The basis and period are labelled ("Q2 FY27 · consolidated" is not allowed; write "Q2 FY27, consolidated"). A `computed` metric gets a footnote mark explained below the grid.
  - **People:** `PeopleList` shows the name, role and change ("Appointed CFO, effective 1 Dec"). The profile is set in Literata because it is filing text, and collapses to 3 lines with a "Show more" toggle.
  - **Brief:** the one-liner in Plex, facts as a two-column list, and the quote in Literata.
  - **Otherwise:** the headline filing subject.
  - **Footer:** "Why it's here", which expands `headline.reasons`; when `members.length` > 1, "{n} filings in this story", which expands the members; "Open filing" (the PDF, new tab) and "Dig in" (`/research/{symbol}`); and "Mark seen", which dims the card and moves it below the unseen ones without removing it.
- **`CaughtUp`.** After the last story: "You're caught up." and the routine drawer below it, grouped by category with counts. Each routine row is subject, symbol and time, and links to the PDF.
- **`StaleNotice`.** When `counts.shown` = 0 and `counts.routine` = 0: the newest filing's time from `latest_filing_at`, plus buttons for the wider windows.

**Tests:**
- vitest with the fixtures:
  - the header copy for 0, 1 and n;
  - `ResultsGrid` renders the fixture's bank card with bank labels and no EBITDA row;
  - Mark seen persists to the store and reorders the cards;
  - the empty fixture renders `StaleNotice` with the formatted `latest_filing_at`.
- Playwright: on Today, change to 7 days; check the request body carries `hours: 168`; open "Why it's here" on the first card; tap the struck count, and the drawer opens.

- [ ] Write the tests, then implement, then run them.
- [ ] Take a screenshot at 390×844 in light and dark mode and review it against the design system. Fix what reads as generic.
- [ ] Commit.

### Task 4: Alerts and holdings

**Files:**
- `src/app/alerts/page.tsx`;
- `src/components/alerts/{Holdings,Sparkline,AlertLog,RulesSheet}.tsx`.

**Behaviour:**
- **The request.** `POST /alerts` with the stored rules; `GET /portfolio`.
- **Holdings.** Rows are symbol (bold) and size, a 20-close `Sparkline` (single series, 2px line in `--ink-2`, last point dot), close, day % (signed with ▲/▼ and colored) and volume ratio. A ratio at or above the rule's multiple is in bold with a "volume" flag word. Rows whose symbol has an alert get a pencil margin bar. Muted symbols show "Muted".
- **Sparkline.** A crosshair tooltip on hover or touch shows the date and close (dataviz interaction rule). It carries an `aria-label`: "20-day close, from ₹X to ₹Y".
- **Alert log.** The `alerts` list, newest first. Each entry is the message, symbol, date and kind. A filing alert links to its story (Today, with a 7-day window, scrolled to `story_id`) or to `/filings/{seq_id}` with `subscribed`.
- **`RulesSheet`** (bottom sheet):
  - volume multiple (a stepper of 0.5 between 1.0 and 10, plus free entry) and price move % (1–20);
  - category checkboxes with plain labels;
  - per-symbol overrides: volume, price and a muted toggle.

  "Save rules" writes the store, closes the sheet and revalidates `/alerts` and `/digest`. The toast reads "Rules saved", and there is a "Reset to defaults" option.

**Tests:**
- vitest: `Sparkline` path math (min and max scaling; a flat series is drawn mid-height with no NaN); the rules sheet clamps invalid input and saves to the store.
- Playwright: lower the volume multiple to 1.0, save, and check that the next `/alerts` request body carries `volume_multiple: 1`.

- [ ] Write the tests, then implement, then run them, then take screenshots and review them.
- [ ] Commit.

### Task 5: Research: list, search, live build

**Files:**
- `src/app/research/page.tsx`;
- `src/components/research/{SearchBox,DossierList,BuildProgress}.tsx`.

**Behaviour:**
- **Page.** A search box sits on top. Below it is `DossierList` from `GET /research`: name, symbol, built date and the ledger tally as a compact segmented bar in status colors, with counts as text.
- **Search.** Typing debounces at 300 ms and calls `/research/search?q=`. Each hit shows its name. Selecting one with a stored dossier navigates to `/research/{SYM}`. Selecting one without opens `BuildProgress`. The symbol is parsed from the hit's `url` (`/company/{SYM}/…`).
- **`BuildProgress`.** Calls `buildDossier`. Progress messages appear as a growing list, the newest in `--ink` and older ones in `--ink-2`, with elapsed seconds and the note "Usually 40–90 s". On `done`, the dossier and excerpts go into the SWR cache, then the app navigates to it. On error, it shows the detail and a "Try again" button. A Cancel button aborts the build.

**Tests:**
- vitest: `BuildProgress` against a mocked `buildDossier`. It renders progress; on `done` it routes; on `error` it shows the detail and a retry; on `incomplete` it shows the stopped message.
- Playwright: search "pers" with a mocked search; pick a symbol that has no stored dossier; check that the mocked SSE (the fixture text) ends on the dossier page.

- [ ] Write the tests, then implement, then run them.
- [ ] Commit.

### Task 6: Dossier

**Files:**
- `src/app/research/[symbol]/page.tsx`;
- `src/components/dossier/{LedgerSection,LedgerRow,Tally,Snapshot,Trajectory,MiniBars,Health,BullBear,CitationChip,SourceSheet,CostLine,SectionNote}.tsx`.

**Behaviour, in section order:**
1. **Title block.** Name, symbol, "Built 9 Nov, 14:05", and `CostLine`: "{calls} model calls, ${usd} at list price, {s} s", or "Served from cache". Then the provenance key: "Serif text is quoted from the company's documents. Everything else is FINN's reading or filed numbers."
2. **Promise ledger.**
   - The `Tally` bar shows the counts per status, plus credibility when it is non-null ("Credibility 62%, from 8 resolved promises").
   - **"Open promises (latest call)"** holds the rows whose `promise.made_in` equals the newest source quarter.
   - **"Track record (earlier calls)"** holds the rest, grouped by `made_in`, newest first.
   - **`LedgerRow`:**
     - the status glyph and word in the left margin (color + glyph + word);
     - the topic in Plex 600;
     - the promise quote in Literata, with a `CitationChip` ("Q4 FY26 call, p. 7");
     - target and horizon when present ("Target 15–18%, FY27");
     - for a `computed` row, the actual ("Delivered 11.2% YoY revenue growth, Q2 FY27") with "Computed from filed financials";
     - the evidence quote in Literata with its chip ("Later: Q1 FY27 call, p. 4");
     - the rationale in `--ink-2`.
   - `dropped` reads "Not mentioned again in the later calls FINN read".
3. **Snapshot.** The points, each followed by its chip.
4. **Trajectory.** Three small single-series charts (no dual axis): Revenue (₹ cr bars), operating margin (% line; "Financing margin" when `lender`) and PAT (₹ cr bars, with negatives below a zero baseline). Years run on a shared x-axis. Each chart gets a header line with its CAGR or bps change, the `read` word ("Growing", "Compressing", "Mixed", "Not enough data") and hover tooltips. A "Show table" toggle gives the same numbers as a table.
5. **Balance sheet and cash.** A definition list of D/E, CFO/PAT (3 y), FCF (3 y), working-capital days (with the 3-year change) and ROCE. Lenders omit the rows that are null. Below it go the flags, each with a level glyph: ● good, ▲ watch, ■ concern.
6. **Bull and bear.** Two lists of 3 points, each with its chip.
7. **Notes.** The `notes` list in `--ink-2` under "What FINN skipped", shown only when it is non-empty.

**`CitationChip` and `SourceSheet`.** Tapping a chip opens a bottom sheet with the source title and page. The page text is set in Literata, with the quote highlighted (a `<mark>` in a pencil tint), and the sheet scrolls to the quote. The text comes from the excerpts in the SWR cache (after a live build) or from `/research/{sym}/source/{id}/{page}`. Matching uses whitespace-insensitive search; with no match, it shows the page unhighlighted. A FACTS chip opens a sheet showing the FACTS line with the note "Computed by FINN from screener's filed financials, not quoted from a document". The sheet links "Open the PDF" to the source `url`.

**Section nulls.** A null section renders `SectionNote` with the matching `notes` line, or else "Not available for this company". Review Focus 5 covers this.

**Tests:**
- vitest with every dossier fixture:
  - no section throws when nulled;
  - the ledger splits into open and track-record groups correctly;
  - dropped is labelled "Not mentioned again";
  - a FACTS chip is not set in the quote font;
  - "Served from cache" shows at $0;
  - credibility is hidden when null;
  - the lender fixture shows "Financing margin" and no CFO/PAT row;
  - `MiniBars` handles negatives and nulls with no NaN in the paths.
- Playwright: the golden path. Today, then Dig in on a story whose symbol has a dossier, the ledger, tapping a chip, and the sheet showing a highlighted quote.

- [ ] Write the tests, then implement, then run them, then take screenshots at 390×844 in light and dark mode and review them.
- [ ] Commit.

### Task 7: PWA, states, full pass

**Files:** `public/sw.js`, `src/components/ServiceWorker.tsx`, `src/components/{Skeleton,ErrorState}.tsx`, and `e2e/*.spec.ts`.

- [ ] **Service worker.**
  - Cache-first for `/_next/static/*`, fonts and icons.
  - Network-first for API GETs (`/research*`, `/portfolio`, `/results/*`), with a cached fallback. A fallback response is tagged by a header the client reads, so the screen can say "Offline: showing what FINN had at 14:05".
  - POSTs are not cached.
  - Registered in production only.
- [ ] **Shared states.** `Skeleton` and `ErrorState` (message plus Retry) are used by every screen. Review Focus 2 covers this.
- [ ] **Full Playwright run** at 390×844 and 360×740. On every screen: no overflow, no console errors, and an axe check with `@axe-core/playwright` (dev dependency) reporting no serious violations.
- [ ] **Lighthouse-style check.** Run `npm run build && npm start` and check the manifest and installability in Chromium (`navigator.serviceWorker.controller` is set after reload).
- [ ] Update `docs/DESIGN.md` with a "Frontend" section (the design system summary and the provenance typography rule) and screenshots in `docs/screenshots/`.
- [ ] Commit.
