# FINN — Project Brief (quick reference)

> Everything about the ENAM Holdings AI Engineer Build Challenge in one place: what they asked for, what they grade, the domain cheat-sheet, our build, and the submission checklist.
> Sources: *FINN: Financial Investment Agent – AI Engineer Build Challenge* (main brief), *Reference: Announcement Categories & Financial Glossary*, and the ENAM AI/ML Engineer JD (IIT Delhi placement).

---

## 1. Summary & key dates

| | |
|---|---|
| **What** | FINN: a **mobile-first financial investment agent** with two modes, **Push** (tells you what changed and why you should care) and **Pull** (researches a company on demand). |
| **Released** | Sun 8 November 2026 |
| **Deadline** | **Sun 15 November 2026** |
| **Deliverable** | Working mobile-first prototype + GitHub repo + AI build history + covering-email writeup |
| **Send to** | **assessment@enam.com** |
| **Subject line** | **IIT Delhi – AI Engineer - 2027** |
| **Role** | AI/ML Engineer, ENAM Holdings (family office, public-markets investing), Mumbai, in-office. The selection process includes "build a working solution using AI-assisted programming, for a given use-case on investing" (this challenge) followed by technical and personal interviews. |

## 2. The problem, and what ENAM is grading

**The problem.** Investors drown in prices, filings, announcements, results and macro data, and most of it doesn't matter. The scarce skill is **filtering**: surfacing the few things that matter and burying the rest, beautifully. FINN should become part of an investor's **daily workflow**: something they reach for through the day that saves time and shows only what's important.

**What they grade:** *"How you build, what you choose to build, and the creativity and judgment behind it — not completeness or polish."*

| Criterion | What it means for us |
|---|---|
| Creativity, product sense, judgment, architecture | Choices must be deliberate and explained. |
| **Thin-but-working > broad-but-broken** | Nail 1–2 workflows. *"A demo that doesn't run is the worst outcome."* |
| "Build the smallest thing that **proves** you can build the real thing well" | Real data, real pipeline, small surface. |
| **No AI slop** | "Core, concise, beautifully presented, and interactive… feel like a product someone thought hard about, not a model filling a template. Density and design both count." |
| Interaction model | "Chat, voice, a copilot, a dashboard, or something we haven't thought of — try more than the obvious." Show a **point of view** on how an investor should interact. |
| **Efficiency = bonus points** | Spend less for the same result: smart model routing (cheap for bulk extraction, strong only where reasoning is needed), caching, chunking. Free tiers are enough. |
| Model choice | No restriction on models; picking the right tool per step is itself evaluated. |
| Frontend | "The heart of the challenge." The backend is "plumbing, not the point." |

## 3. Requirements

### 3.1 Companies
- **Portfolio:** a mock portfolio of **15–20 NSE/BSE-listed companies**, mixed across sectors and sizes so the demo is interesting.
- **Ad-hoc research set:** **3–5 companies** (may be outside the portfolio) to demo Pull on.
- **Must generalise:** research must work on **any NSE ticker** with available data. *"We may point it at a company you didn't pick."*

### 3.2 Backend data (guided; "don't over-engineer")
1. **Price & volume (end-of-day)** for the portfolio: Yahoo Finance / `yfinance` (`.NS` = NSE, `.BO` = BSE, e.g. `RELIANCE.NS`), or anything equivalent.
2. **Corporate announcements / filings** from NSE/BSE. The reference taxonomy (§5) is optional guidance.
3. **Company fundamentals:** annual reports + concall (earnings-call) transcripts, via links on screener.in or company IR sites.

### 3.3 Push: the app reaches out
**(a) Windowed digest.** For a window the user picks (**default last 24h**, user can change it): every filing across the portfolio, **filtered and prioritised**. What matters shows first; routine filings are collapsed or hidden.

**(b) Triggered alerts.** Fire when something crosses a threshold:
- a **material announcement of a type the user cares about** (results, M&A, management change, …);
- an **unusual EOD move**, e.g. volume > ~2× recent average, or price move beyond ±X% in a day. **Thresholds must be configurable**: the user decides what "unusual" means.

**How pushed items are presented.** Two examples ENAM explicitly loves:
- **Management change:** not just "CFO resigned". Pull a short **background/bio of the incoming person** (e.g. LinkedIn) so the user instantly knows who they are and where they came from.
- **Quarterly results:** from the actual results filing, a first cut of **Revenue, EBITDA, PBT, PAT**, this quarter vs **last quarter (QoQ)** and vs **same quarter last year (YoY)**.

For every other type, *we* decide what earns attention: a one-line summary, or just the filing at the right priority. *"That judgment is the point."*

### 3.4 Pull: you ask it to dig in
On-demand analysis **grounded in fundamentals (annual reports + concall transcripts)**. A menu; pick what to build and how deep to go:

| # | Output | What it is |
|---|---|---|
| 1 | Business snapshot | What the company does, segments, revenue mix |
| 2 | Financial snapshot | Current headline numbers: revenue, margins, PAT, key ratios |
| 3 | Trajectory | Multi-year direction: what's growing, what's compressing |
| 4 | Balance sheet | Debt, leverage, working-capital cycle, funding structure |
| 5 | Cash quality | Cash-flow trend and cash conversion: do profits turn into cash? |
| 6 | Narrative vs numbers | Where management's story and the financials agree or diverge |
| 7 | Guidance | What management explicitly guided on headline numbers (growth, margins, capex) |
| 8 | Bull vs bear | A tight case each way |

**The worked example ENAM values most (numbers vs narrative):** take the **last four quarters** and, against management's own headline guidance and growth commentary, show **what was promised vs what was delivered**. *"This is the difference between summarising management and analysing them."*

**Discipline (hard rule):** Pull uses **primary sources only** (annual reports + transcripts). No broker notes, no news, no research reports, and **no leaning on the model's own outside knowledge** of the company. (Push-side enrichment such as a person's professional background is fine.)

### 3.5 Interaction model
Entirely ours. Experiment, mobile-first, with a point of view on *how* an investor should interact, not just *what* data to show.

## 4. Data sources: probe findings (8 Nov 2026, from a home connection)

| Source | Status | Notes / gotchas |
|---|---|---|
| NSE `https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=TCS` | ✅ works | Returned 3,384 TCS filings. Fields: `symbol, sm_name, desc` (NSE's own category), `attchmntText` (one-line subject), `attchmntFile` (PDF on nsearchives), `an_dt`, `sort_date`, `seq_id`, `smIndustry`, `hasXbrl`. Homepage returns 403 to curl, but the API answered with browser-like headers + Referer. Cloud IPs may be blocked; to be tested from HF Spaces. |
| BSE `api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData` | ❌ Access Denied | Not used for filings. BSE-hosted PDFs (linked from screener) still to be verified. |
| screener.in `/company/<SYMBOL>/consolidated/` | ✅ works | Sections `#quarters #profit-loss #balance-sheet #cash-flow #ratios #shareholding #documents`. Documents list Annual Reports (TCS: 2013–2026) and Concalls (Transcript / PPT / REC links, mostly BSE-hosted PDFs). |
| Yahoo chart API (raw) | ⚠️ 429 | `yfinance` (cookie + crumb) to be verified; fallback needed (NSE historical endpoint or another EOD source). |

Most-common NSE `desc` values for TCS: Press Release, Updates, Analysts/Institutional Investor Meet/Con. Call Updates, **Loss of Share Certificates**, **Copy of Newspaper Publication**, Dividend, Record Date, Financial Result Updates, Outcome of Board Meeting, Shareholders meeting, News Clarification, Disclosure under SEBI Takeover Regulations. The bold ones are pure noise.

Timing: Nov 2026 is **Q2 FY27 results season** (quarter = Jul–Sep 2026), so filings will be full of real results, concalls and board outcomes.

## 5. Announcement taxonomy (from the reference doc) + our materiality bases

| Category | What goes in it | FINN base score |
|---|---|---|
| results | Quarterly/annual results, the approving board meeting, results decks, shareholder letters, results-published ads | 90 |
| M&A | Acquisition, merger, demerger, JV, investing in or selling a stake in a subsidiary | 85 |
| management_change | CEO, CFO, MD or director joining, resigning or retiring | 80 (CXO ↑, independent director ↓) |
| pledging | Promoter pledging, releasing or changing pledge status | 75 |
| litigation | Lawsuits, regulatory orders, fines, warnings, insolvency/restructuring | 75 |
| credit_rating | Assigning, upgrading, downgrading or reaffirming a rating | 70 (downgrade ↑, reaffirm ↓↓) |
| fund_raise | Rights issue, QIP, preferential allotment, buyback, commercial paper | 70 |
| capex | New plant, facility, capacity expansion | 60 |
| insider_trading | Promoter/insider buying or selling personal shares | 50 |
| bonus_split | Bonus issue or stock split | 40 |
| press_release | Order wins, products, partnerships, rumour clarifications | 35 (big order vs revenue ↑) |
| earnings_call | Concall notice, transcript, recording | 30 (transcript ↑, since it feeds the Promise Ledger) |
| dividend | Cash dividend + record date | 30 |
| agm_egm | AGM/EGM notice and result | 15 |
| postal_ballot | Postal ballot notice and result | 15 |
| investor_meetings | 1:1 or group investor meetings, conferences | 10 |
| unclassified | ESOP allotments, compliance certificates, ESG reports, auditor appointments | 5 |

Noise floor: **Critical ≥ 75 · Important ≥ 45 · Everything**.

## 6. Glossary cheat-sheet

**Documents**
- **Annual Report (AR):** yearly disclosure; business overview, MD&A, audited P&L / balance sheet / cash flow, notes, auditor's report. The richest primary source.
- **Quarterly results:** quarterly financials filed with the exchanges.
- **Concall transcript:** management discusses results and answers analysts. Where **guidance and tone** live.
- **Investor presentation:** management's slides on strategy, KPIs and segments.
- **Exchange filing:** any disclosure filed with NSE/BSE; the raw Push feed.
- **Primary vs secondary:** primary = from the company (filings, reports, transcripts). Secondary = commentary (news, broker notes). **Pull = primary only.**

**Headline numbers**
- **Revenue:** total sales, the top line.
- **EBITDA:** earnings before interest, tax, depreciation and amortisation; a proxy for operating profitability. If a filing doesn't report it, FINN computes `EBITDA = PBT + finance cost + D&A − other income` and labels it *computed*.
- **PBT:** profit before tax.
- **PAT:** profit after tax, i.e. net profit, the bottom line.
- **Margin:** profit ÷ revenue (e.g. EBITDA margin).
- **QoQ:** vs the immediately previous quarter.
- **YoY:** vs the same quarter a year ago; removes seasonality.

**Balance sheet & cash**
- **Debt / leverage; D/E:** total debt ÷ shareholders' equity.
- **Working-capital cycle:** inventory + receivables − payables, in days. A lengthening cycle drains cash.
- **Cash from operations (CFO):** cash the core business generates.
- **Cash conversion:** CFO ÷ PAT. Persistent profit without cash is a red flag.
- **FCF:** CFO − capex.
- **ROCE / ROE:** return on capital employed / on equity.
- **Contingent liabilities:** potential obligations disclosed in the notes.
- **RPTs:** related-party transactions, a place value can leak.
- **Auditor's qualification:** the auditor flags a concern; dig deeper.

**Corporate actions & market**
- **NSE / BSE:** the two exchanges.
- **Ticker:** a stock's code; `.NS` / `.BO` on Yahoo.
- **Market cap:** price × shares.
- **Promoter:** controlling shareholder group.
- **Pledging:** promoter shares used as loan collateral (a risk signal).
- **Material announcement:** could move the stock.
- **Guidance:** management's stated forward expectations.
- **Capex:** spend on long-term assets.
- **Dividend / record date:** the cash payout, and the cut-off date for who receives it.
- **Bonus / split:** more shares, no cash.
- **Buyback:** the company buys back its own shares.
- **Rights / QIP / preferential:** ways of raising fresh equity.
- **EOD:** end-of-day close price and volume.

**Indian fiscal calendar:** FY27 = Apr 2026 – Mar 2027.
- Q1 = Apr–Jun
- Q2 = Jul–Sep
- Q3 = Oct–Dec
- Q4 = Jan–Mar

## 7. Our build (summary; full detail in [DESIGN.md](DESIGN.md))

**Point of view:** *"A feed that ends, and a memory that holds management to its word."*

- **Today (Push).** A finite, ranked digest ("4 things matter · 37 routine hidden").
  - Filings belonging to one event are clustered into one story card.
  - Each category gets a bespoke card:
    - Results: Revenue/EBITDA/PBT/PAT, QoQ/YoY, plus a "vs promise" chip.
    - People: the incoming person's bio.
    - Deal / Rating / Pledge / Litigation: a one-liner.
  - Every card says why it ranks where it does, and the feed ends with **"You're caught up."**
- **Alerts & Portfolio.** Holdings with sparklines and volume multiples. A rules editor for volume ×, price ±% and category subscriptions (stored on the device). An alert log.
- **Research (Pull).** Any NSE ticker produces a Dossier, built live with streamed progress for unknown tickers.
  - **Promise Ledger** (promised vs delivered over the last 4 quarters, with verbatim quotes and page citations).
  - Snapshot, Trajectory, Balance sheet & cash quality (computed in Python), Bull vs Bear.
  - Every claim is cited, and claims that can't be verified against the source text are dropped.
- **Model routing:**
  - Rules first (free).
  - Groq `openai/gpt-oss-120b`, batched 20 per call, for ambiguous classification and one-liners.
  - Gemini 3.5 Flash-Lite (3.1 Flash-Lite fallback) for transcript extraction; results numbers come from NSE XBRL with no model.
  - The same Flash-Lite route for ledger judgment and synthesis; a ledger verdict counts only with a verbatim quote from a later call (Pro has no free tier; 3.8 Flash was unreliable on it).
- **Efficiency:** content-hash caching of every document and LLM call; every call logged in a per-call cost ledger shown in the UI.
- **Arithmetic is never done by the LLM.**
- **Stack:** FastAPI + SQLite on Hugging Face Spaces (Docker); Next.js PWA on Vercel.

## 8. Build & run (filled in as the build progresses)

```bash
# backend
cd backend
cp .env.example .env          # add GEMINI_API_KEY, GROQ_API_KEY
uv sync
uv run pytest
uv run python scripts/refresh.py --days 30 --out seed/finn.sqlite  # filings, prices, classifications
uv run python scripts/research.py PERSISTENT TCS --out seed/finn.sqlite  # precompute demo dossiers
uv run uvicorn finn.api.main:app --reload --port 8000

# frontend
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Deploy:
- **Backend:** Docker Space on Hugging Face, port 7860, with keys set as Space secrets.
- **Frontend:** Vercel, with env `NEXT_PUBLIC_API_URL` set to the Space URL.

## 9. Submission checklist (due Sun 15 Nov 2026)

- [ ] **Mobile-first prototype link.** Deployed and easy to try on a phone. Test on a real phone first, and check that the first load works after the Space has been idle.
- [ ] **GitHub repository** (public), with a README containing the live link, architecture, eval and cost numbers, and how to run.
- [ ] **AI build history.** Claude Code session exports (`ai-history/`, redacted, reviewed by me) and/or share links for any other LLM chats used.
- [ ] **Covering email writeup**, short, covering:
  - [ ] what I built
  - [ ] key decisions and trade-offs
  - [ ] what I deliberately left out
  - [ ] where I'd take it next
- [ ] Email to **assessment@enam.com**
- [ ] Subject exactly: **IIT Delhi – AI Engineer - 2027**
- [ ] Links and attachments included, and sent before the deadline.

## 10. Interview prep: questions our choices invite

- **Why a finite feed?** Attention is the scarce resource. An end state ("caught up") is a feature; infinite scroll is the problem ENAM describes.
- **Why is materiality scoring rules-first?** It's explainable, free and deterministic; the LLM only handles the ambiguous tail. Show the classification eval numbers.
- **How do you stop hallucinated numbers?**
  - Arithmetic is done in Python.
  - Extracted figures are cross-checked against screener's quarterly table.
  - Quotes are verified against the source text before display.
- **How do you keep Pull primary-only?** Prompts constrain the model to the provided excerpts, every claim needs a citation, unverifiable claims are dropped, and nothing from news or brokers is ever fetched.
- **Cost?** Show the per-dossier and per-digest cost ledger, and explain why each step uses its model.
- **What breaks at scale?**
  - Scraping fragility: NSE blocking, layout changes.
  - Free-tier rate limits.
  - SQLite is single-writer.
  - Moving to production: an exchange data vendor, Postgres, a queue for ingestion, and per-user auth.
