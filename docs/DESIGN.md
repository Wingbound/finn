# FINN — Design & Decisions

## Context

This is the design for the ENAM Holdings AI Engineer Build Challenge. The task: build **FINN**, a mobile-first financial investment agent with **Push** (proactive digest + threshold alerts) and **Pull** (on-demand company research grounded only in annual reports + concall transcripts). Released 8 Nov 2026, **due 15 Nov 2026**. ENAM grades creativity, product sense, judgment and architecture — not completeness. "Thin-but-working beats broad-but-broken"; a demo that doesn't run is the worst outcome; cost efficiency (model routing, caching, chunking) earns bonus points; the AI build history (this Claude Code session) is itself a deliverable.

User decisions (8 Nov): LLMs = **Gemini (free) + Groq (free)**; backend hosting = **Hugging Face Spaces**; frontend = Vercel; Claude makes the product/design calls, user reviews this plan.

Data-source probe results (8 Nov, from user's machine):
- NSE `api/corporate-announcements?index=equities&symbol=X` → **works** (3,384 TCS filings; fields: `desc`, `attchmntText`, `attchmntFile` PDF, `an_dt`, `sort_date`, `seq_id`, `smIndustry`, `hasXbrl`).
- screener.in company page → **works**; has `#quarters #profit-loss #balance-sheet #cash-flow #ratios #shareholding #documents`; documents list Annual Report PDFs (2013–2026) and concall Transcript/PPT links (mostly BSE-hosted PDFs).
- BSE API → **Access Denied** (use NSE for filings; BSE PDF links from screener still downloadable — verify).
- Yahoo raw chart API → 429 rate-limited; yfinance must be verified, with a fallback (NSE historical endpoint or stooq).
- Machine: Python 3.13, Node 22, uv 0.13. No `gh`, no Docker, no API keys yet.

---

## 1. Product concept (the point of view)

**"A feed that ends, and a memory that holds management to its word."**

Most investor tools are infinite feeds. FINN is *finite*: it tells you how many things matter today, shows only those, collapses the rest into a counted "routine" drawer, and ends with **"You're caught up."** And FINN *remembers*: it reads every concall, logs what management promised, and when results land the push card is automatically graded against those promises. Push and Pull are one loop, not two tabs.

### Surfaces (mobile-first PWA, bottom tab bar)

1. **Today (Push digest)**
   - Header: *"4 things matter · 37 routine filings hidden"* + window chips (24h default · 3d · 7d · custom range) + a 3-step **noise floor** control (Critical / Important / Everything).
   - **Event clustering**: the 3–5 filings one event generates (board-meeting outcome + results + press release + newspaper ad) collapse into **one story card** ("4 filings → 1 story").
   - Bespoke card per category — the judgment the brief asks for:
     - **Results card**: Revenue / EBITDA / PBT / PAT grid, QoQ & YoY deltas, margin, plus a **"vs promise" chip** from the Promise Ledger (e.g. "Guided 15–18% growth → delivered 11%: MISSED").
     - **People card** (management change): who's in/out, role, and a short bio. Source 1 is the filing itself (SEBI LODR Reg 30 appointment filings must include a "brief profile"). Source 2 is Gemini with Google Search grounding for LinkedIn-style background, linked. Push-side enrichment is explicitly allowed.
     - **Deal / Rating / Pledge / Litigation / Fund-raise cards**: one-line "why it matters" summary (cheap model) + key fields (size, counterparty, rating up/down arrow).
     - Everything else: filing surfaced at its priority, no summary (no tokens spent on noise).
   - Each card shows a **"why it ranks here"** chip, so the materiality score is explainable, plus actions: **Dig in** (opens the dossier at the relevant section), **Open filing** (PDF), **Mark seen**.
   - Ends with a *"You're caught up"* state and a "routine (37)" accordion grouped by category.
2. **Alerts & Portfolio (watch + rules)**
   - Holdings list: price, day %, 20-day sparkline, volume vs 20-day average (×), flagged rows.
   - **Rules editor**: global thresholds (volume multiple, default 2.0×; price move, default ±5%) with per-stock overrides; category subscriptions (results, M&A, management change, rating, pledging, litigation…). Rules persist on the device (see §7b); alerts re-evaluate immediately on save.
   - Alert log: triggered alerts, newest first, each linking to its card.
3. **Research (Pull)**: search *any* NSE ticker → **Dossier**
   - Known tickers load instantly from cache. Unknown tickers build live, with **streamed progress** (SSE): "Found 4 transcripts, 2 annual reports → reading Q2 FY27 call → extracting guidance → checking delivery…".
   - Sections (menu items chosen, in order of value):
     1. **Promise Ledger** (hero, the "numbers vs narrative" worked example): last 4 quarters of management's own headline guidance, each row with verbatim quote, source + page, target, actual, and status (Kept / Partly / Missed / Pending / Quietly dropped).
     2. **Snapshot**: what the company does, segments, revenue mix (from the AR) + headline numbers.
     3. **Trajectory**: multi-year revenue, EBITDA margin and PAT, with a "growing vs compressing" read.
     4. **Balance sheet & cash quality**: D/E, working-capital days, CFO/PAT conversion, FCF. Computed **deterministically in Python** from screener tables; the LLM only narrates.
     5. **Bull vs Bear**: three tight points each, every point cited.
   - Every LLM-written claim carries a **citation chip** (doc + page). Tapping it opens the source excerpt. Claims whose quotes can't be found in the source text are dropped before display (grounding guard).
4. **Stretch, only if Days 1–5 land:**
   - "Ask FINN" bottom sheet: grounded Q&A over one company's docs, with citations.
   - Real **Web Push** notifications for installed-PWA alerts.
   - "Listen" 60-second brief via browser TTS (free).

Deliberately out of scope (goes in the writeup): intraday data, broker/news sentiment, auth and multi-user, portfolio P&L/accounting, BSE as a filing source.

---

## 2. Architecture

```
NSE announcements ─┐                       ┌─ /digest?window=  (clustered, ranked)
yfinance EOD ──────┼─► ingest ─► SQLite ◄──┼─ /alerts, /portfolio, /rules
screener.in ───────┘      │                └─ /research/{ticker}  (SSE build + cached dossier)
                          ▼
              classify (rules → Groq) ─► materiality score ─► enrich (results / people / one-liners)
                                                                    │
                       research: screener tables (deterministic math) + transcripts/AR
                                 ─► guidance extraction (cheap) ─► ledger + synthesis (strong) ─► grounding guard
```

**Backend:** Python 3.12+, FastAPI, uv, SQLite (WAL), httpx, PyMuPDF, yfinance, APScheduler. Deployed as Vercel Python functions serving a read-only snapshot (see Hosting below).
**Frontend:** Next.js (App Router) + TypeScript + Tailwind, installable PWA (manifest + service worker), deployed on Vercel; `NEXT_PUBLIC_API_URL` points to the Vercel backend deployment.

### Model routing (verify current free-tier model IDs and limits at build time via each provider's list-models endpoint; never hard-code from memory)

| Task | Tier | Provider/model class | Why |
|---|---|---|---|
| Filing classification | 0 | Deterministic rules on NSE `desc` + subject keywords | Covers most volume at zero cost |
| Ambiguous classification + one-liners | 1 | Groq `openai/gpt-oss-120b`, reasoning effort medium, batched 20 filings/call, JSON mode | Fast, free; 91.3% vs 85.6% for gpt-oss-20b on the eval, ~$0.001/batch at list price (EVALS.md) |
| Results number extraction | 2 | XBRL (deterministic, no LLM) | NSE publishes structured XBRL for every results filing; no model needed |
| Transcript guidance extraction (per transcript) | 2 | Gemini Flash-Lite/Flash, chunked by section | Bulk extraction |
| Ledger judgment, narrative vs numbers, bull/bear | 3 | Gemini Pro-class (or Flash with thinking) | Only place real reasoning is needed; once per company, cached |
| People bio | 2 | Gemini + Google Search grounding | Push-side enrichment allowed |

- **Arithmetic stays out of the LLM.** QoQ/YoY %, margins, D/E, CFO/PAT and FCF are computed in Python. EBITDA, when not reported, = PBT + finance cost + D&A − other income, flagged "computed".
- **Caching**: content-hash cache for every downloaded doc and every LLM call (`sha256(model + prompt + doc_hash)`), so re-running costs ₹0. Dossiers are cached per (ticker, doc-set hash).
- **Cost ledger**: every LLM call logs tokens/model/latency. The UI shows "this dossier: N calls, ~₹X, Ys", and README reports the totals — a direct answer to the efficiency criterion.
- **Rate-limit aware**: token-bucket per provider and backoff on 429. Demo-set dossiers are precomputed so the live demo never burns quota.
- **Model IDs are checked against each provider's list-models endpoint, never typed from memory** (2026-11-09). That check found Groq had retired its Llama models, so classification moved to gpt-oss-120b. It also found that `gemini-3.8-flash` is listed and priced, but on the free tier only 1 of 7 calls succeeded that day; the rest were 503s or 45-second hangs. `gemini-3.5-flash-lite` answered 5 of 5 in about 1.5 s. Plan 2 therefore gives each Gemini task a fallback chain, so a hang on the primary model moves to the fallback within one short timeout. Plan 2 also picks the primary model from the results-extraction eval, not from the version number.

### Materiality score (deterministic, explainable)
`score = category_base × subtype_modifier × user_subscription_boost (+ price-reaction bump)`.
- Bases (guide): results 90 · M&A 85 · management_change 80 (CEO/CFO/MD ↑, independent director ↓) · pledging 75 · litigation 75 · credit_rating 70 (downgrade ↑, reaffirm ↓↓) · fund_raise 70 · capex 60 · insider_trading 50 · bonus_split 40 · press_release 35 (order-win size vs revenue ↑) · earnings_call 30 (transcript ↑, it feeds the ledger) · dividend 30 · agm_egm/postal_ballot 15 · investor_meetings 10 · unclassified 5.
- Hidden as noise: "Loss of Share Certificates", "Copy of Newspaper Publication", duplicate filings.
- Noise floor thresholds: Critical ≥ 75, Important ≥ 45, Everything = all.

### Hosting (2026-11-09)

Docker Spaces on Hugging Face now need HF PRO, so the backend runs on Vercel Python functions instead. The deployed API is read-only over the committed SQLite snapshot. `scripts/refresh.py` runs out-of-band (locally or on a schedule), is the only code that touches NSE, Yahoo, screener or the LLMs, and its output replaces the snapshot.

### Robustness ("demo never breaks")
Every external fetch is cached with an `as_of` timestamp. The deployed API boots from the committed **seeded SQLite snapshot** and never fetches. A GitHub Actions cron (or a local `scripts/refresh.py`) ingests out-of-band and commits a fresh snapshot.

---

## 3. Repo layout (new git repo at `ENAM/finn/`; the PDFs stay outside it, since the JD carries the student ID)

```
finn/
  README.md                      # what/why, live links, architecture diagram, eval + cost numbers, run locally
  docs/PROJECT_BRIEF.md          # the requested reference doc (see §6)
  docs/DESIGN.md                 # this design, decisions & trade-offs (feeds the email writeup)
  docs/EVALS.md                  # classification accuracy, extraction accuracy, citation-verification rate, cost
  backend/
    pyproject.toml, Dockerfile, .env.example
    finn/config.py  db.py  models.py  portfolio.yaml  rules.py
    finn/llm/router.py  cache.py  costs.py  prompts/
    finn/ingest/nse.py  prices.py  screener.py  pdfs.py
    finn/classify/rules.py  llm.py  materiality.py  cluster.py
    finn/enrich/results.py  people.py  oneliner.py
    finn/research/financials.py  docs.py  guidance.py  ledger.py  synthesis.py  grounding.py  pipeline.py
    finn/api/main.py  routes_*.py  sse.py
    scripts/seed.py  refresh.py  eval_classify.py  eval_results.py  export_history.py
    tests/fixtures/ (recorded NSE JSON, screener HTML, sample PDFs' text)  tests/test_*.py
  frontend/  (Next.js app: app/(today|alerts|research)/, components/cards/*, lib/api.ts, public/manifest.json)
  ai-history/                    # exported Claude Code transcripts (rendered to Markdown)
  .github/workflows/refresh.yml  # only if HF can't reach NSE/Yahoo
```

## 4. Companies

- **Portfolio (18)**, chosen with data rather than by guessing. Start from a candidate pool across sectors and sizes (large: RELIANCE, TCS, HDFCBANK, ITC, LT, SUNPHARMA, MARUTI, BHARTIARTL; mid: TRENT, DIXON, PERSISTENT, POLYCAB; small/specialty: e.g. a chemical, a capital-goods name, a PSU, a pharma, a consumer brand). Pick the final 18 by ranking candidates on material-filing activity in the last 30 days. This is Q2 FY27 results season, so the demo will be full of real results, rating actions and management changes.
- **Research demo set (4)**: at least 2 outside the portfolio, chosen for rich guidance history (capex/margin/growth guidance across 4+ transcripts). One should have visible misses, so the ledger shows both colors.
- Generalisation test: run the research pipeline on 3 random NSE tickers not in either set before submitting.

## 5. Build sequence (7 days; each day ends with something runnable)

**Day 0 — Sun 8 Nov (today, after approval)**
1. `git init finn/`, `.gitignore` (.env, data caches, PDFs), write `docs/PROJECT_BRIEF.md` and `docs/DESIGN.md`.
2. Spikes, with parallel subagents (superpowers:dispatching-parallel-agents):
   - NSE ingest with cookie session + retries.
   - yfinance batch download + fallback.
   - screener parse (tables + documents).
   - PDF download/extraction for one results filing and one transcript.
   - Record fixtures from each.
3. Deploy a throwaway FastAPI probe to HF Spaces that hits NSE/Yahoo/screener. **This decides the refresh strategy.**
4. User provides keys (see §7).

**Day 1 — Mon 9 Nov · Push backbone**
- SQLite schema, NSE ingest, rule classifier, Groq fallback, materiality, clustering, `/digest`.
- Gold set: 104 filings (AI-labelled, see EVALS.md) → `eval_classify.py`. Use superpowers:test-driven-development for rules, scoring and clustering.

**Day 2 — Tue 10 Nov · Push enrichment + alerts**
- Results from NSE XBRL, with the figures computed in Python and cross-checked against the screener quarterly table (`scripts/eval_results.py`; no LLM).
- People enrichment, one-liners.
- Price ingest + alert engine + `/rules` and `/alerts`.
- `eval_results.py` over ~15 results filings.

**Day 3 — Wed 11 Nov · Pull engine**
- Ticker resolve via screener search.
- Deterministic financials module.
- Transcript guidance extraction (per-transcript, cached).
- Ledger matching: quantitative = deterministic compare; qualitative = strong model.
- Synthesis + grounding guard + SSE progress; precompute the demo set.

**Day 4 — Thu 12 Nov · Frontend**
- Invoke `example-skills:frontend-design` + `dataviz` first.
- Design tokens (light/dark, tabular numerals, one accent), Today feed with bespoke cards, Alerts & rules, Research search + Dossier + citation sheet.
- PWA manifest.

**Day 5 — Fri 13 Nov · Integrate + deploy**
- Vercel (backend Python functions + frontend), secrets in Vercel env.
- Playwright MCP at iPhone/Android viewports: screenshots, console errors, golden-path e2e.
- Polish loading/empty/error states. Stretch features only if all of this is green.

**Day 6 — Sat 14 Nov · Prove it**
- Eval + cost numbers into `docs/EVALS.md`/README.
- Generalisation run on 3 unseen tickers.
- `code-review`, `simplify`, `security-review` (no keys in repo or history).
- Export AI history (`scripts/export_history.py` renders `~/.claude/projects/-home-snig-Desktop-Sem-9-Placement-CV-ENAM/*.jsonl` to Markdown).
- Draft the covering email; run `humanizer` over it.

**Day 7 — Sun 15 Nov · Buffer + submit** (user sends the email; Claude never sends it).

Execution method: after approval, superpowers:writing-plans produces the task-level plan inside the repo, then superpowers:subagent-driven-development runs the independent backend modules in parallel. Use superpowers:systematic-debugging for scraper failures and superpowers:verification-before-completion before any "done" claim.

## 6. `docs/PROJECT_BRIEF.md` (the reference doc the user asked for) — sections
1. One-paragraph summary + key dates (released 8 Nov, due 15 Nov 2026).
2. The problem & what ENAM evaluates (creativity, product sense, judgment, architecture; thin-but-working; no AI slop; efficiency bonus).
3. Requirements, split into **explicit** and **examples/menu**:
   - Push: windowed digest (default 24h, user-chosen window); triggered alerts with configurable volume/price thresholds and category subscriptions; management-change bio; results QoQ/YoY on Revenue/EBITDA/PBT/PAT.
   - Pull: the 8-item menu, the numbers-vs-narrative worked example, and the primary-sources-only rule.
   - Companies: 15–20 portfolio, 3–5 research, must generalise to any NSE ticker.
4. Data sources + probe findings + gotchas (NSE works; BSE API blocked; Yahoo rate-limits; screener structure).
5. Announcement taxonomy table (from the reference PDF) + our materiality bases.
6. Glossary condensed (Revenue/EBITDA/PBT/PAT/margin/QoQ/YoY, D/E, WC cycle, CFO, FCF, ROCE/ROE, pledging, etc.).
7. Our design summary (link to DESIGN.md), model routing, cost discipline.
8. Build & run instructions (local dev, env vars, seeding, tests, deploy to HF + Vercel).
9. **Submission checklist**: deployed phone-friendly link · GitHub repo (public) · AI build history (exports/links) · covering-email writeup (built / decisions & trade-offs / left out / next) · to **assessment@enam.com** · subject **"IIT Delhi – AI Engineer - 2027"** · by 15 Nov 2026.
10. Interview prep notes: the questions our choices invite, and the answers.

## 7. What the user needs to do (Claude can't)
- Get a **Gemini API key** (aistudio.google.com) and a **Groq API key** (console.groq.com) and put them in `finn/backend/.env` (Claude will create `.env.example`).
- Create **Hugging Face** (write token), **Vercel**, and **GitHub** accounts/repos, or install `gh` and log in. Claude will give exact commands; logins use `! <command>` in the prompt.
- Test on their own phone on Day 5; send the final email on Day 7.

## 7b. Calls Claude made (please check these while reading)
- **User state lives on the device, not the server.** Alert rules, "seen" marks and the noise floor live in localStorage and are sent with each request; the server computes alerts statelessly from EOD data + the rules. Each evaluator gets their own settings, nothing is lost when the HF Space restarts (its disk is ephemeral), and no auth is needed.
- **Banks/NBFCs get sector-aware metrics.** EBITDA means little for a bank, so results cards for financials show Total income / NII, Pre-provision operating profit, PBT and PAT, with a note on why. One bank stays in the portfolio to show this.
- **Consolidated over standalone** when both exist; standalone is labelled when it's the only one. All money in ₹ crore. Indian fiscal quarter labels (Q2 FY27 = Jul–Sep 2026).
- **Ledger window**: promises from the last 4 concalls, checked against the following quarter's reported numbers and later calls. Quantitative targets are compared in code; qualitative ones are judged by the strong model, with the quote shown.
- **AI history**: exported to Markdown with the student ID and email redacted. The user reviews it before it goes in the public repo, or shares it as an attachment instead.
- **Repo is public**, so ENAM can open it without access requests.
- **Builder check** done inline by Claude (no extra subagent). The questions it raised are answered by the calls above.

## 8. Verification (end-to-end)
- `uv run pytest`: parsers on recorded fixtures, scoring/clustering, QoQ/YoY/ratio math, grounding guard, rules engine (LLM calls mocked).
- `uv run python scripts/eval_classify.py` reports accuracy and confusion on the gold set; target ≥ 90% on material categories.
- `uv run python scripts/eval_results.py` compares extracted numbers vs the screener quarterly table; target ≥ 90% within 1%.
- Research pipeline on 3 unseen tickers completes, with ≥ 95% of displayed quotes verified in source text.
- Deployed app: Playwright MCP at 390×844, covering Today → card → Dig in → Ledger → citation, a rules change producing a new alert, and an unknown-ticker live build. No console errors. Cold start measured.
- Manual check on a real phone (user) + PWA install.
- Final `security-review`: no secrets in repo or git history.
