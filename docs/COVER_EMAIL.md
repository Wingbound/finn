<!--
Draft of the covering email. Fill in the bracketed name, programme, entry number and phone in your
mail client when you send it. Do not fill them in here: this repo is public.
-->

To: assessment@enam.com
Subject: IIT Delhi – AI Engineer - 2027

Dear ENAM team,

Here is my submission for the AI Engineer build challenge.

- Prototype (best on a phone, and installable): https://finn-qx98.vercel.app
- Code: https://github.com/Wingbound/finn
- AI build history: https://github.com/Wingbound/finn/tree/main/ai-history (the plans, task ledgers, reviews and the redacted Claude Code session)

What I built

FINN does both parts of the brief.

On the push side, it classifies every NSE filing for an 18-stock portfolio, using rules first and an LLM only for what the rules miss. It then scores the filings and groups them into stories. The Today screen says how many things matter, strikes through the routine filings, and ends with "You're caught up." Results cards show Revenue, EBITDA, PBT and PAT with QoQ and YoY changes computed from NSE's XBRL, and banks and NBFCs get their own lines. A management-change card carries the person's profile as written in the filing. Alerts follow thresholds and filing types that you set on the phone, on prices from NSE's own end-of-day service (Yahoo only as a fallback), so filings, results and prices all come from NSE. On a quiet day Today says so and shows what the last week held. A Listen button reads the brief aloud in about a minute, in the phone's own voice, at no cost.

On the pull side, FINN reads the last four earnings calls and the latest annual report of any NSE company and builds a dossier. The dossier opens with a Promise Ledger: each thing management said it would do, quoted with its page and graded against the calls that came after. Every claim has a citation that opens the source page with the quote highlighted.

The two halves meet on the results card. When a holding reports, its card shows what management promised on recent calls, quoted with call and page, next to the filed numbers. When the quote names the same line, a short sentence sets this quarter beside the target, as one quarter of the year rather than a verdict. Every holding has a dossier, so every results card can do this.

Key decisions and trade-offs

- The models never do arithmetic. Python computes QoQ, YoY, margins, CAGR and the balance-sheet ratios. Results come from XBRL rather than from an LLM reading PDFs, and 68 of 70 figures match screener.
- A promise counts as kept or missed only when a later call contains a verbatim quote that shows it. Two hand audits found 8 of 31 verdicts wrong, all in mechanical ways: a restated target read as delivery, a figure on the wrong side of the target, evidence about another period or another measure. I added code checks that can only downgrade a verdict. Across all 23 dossiers, 14 of the 23 remaining verdicts are correct, 9 are debatable and none is wrong. Most promises stay pending, and the app says why for each one.
- Model calls are routed to the cheapest model that does the job. Groq's gpt-oss-120b classifies filings (91.3% on a hand-labelled set of 104, at about $0.001 per 20 filings). Gemini Flash-Lite extracts guidance from transcripts, and Gemini 3.5 Flash is used only for judgment and synthesis. A dossier takes about 9 calls and costs $0.03 to $0.07 at list price. Every call is cached and logged.
- There are no accounts. Alert rules and settings stay on the device and go with each request, so the server holds no user state.

What I left out

I left out intraday data and news or broker sentiment, since the brief asks for primary sources. I also left out BSE filings (its API refuses automated clients), logins and portfolio P&L. The brief suggests a web background for a new appointee; neither free tier includes web search, so the card quotes the profile the company filed under SEBI's disclosure rules. A dossier built live for a new company is cached on the server instance that built it, not in a shared store.

Where I would take it next

I would keep live builds in a shared store, run the ledger over eight quarters with a larger hand-audited set, and add push notifications for alerts.

Thank you for an interesting problem. I'd be glad to walk you through any part of it.

Best regards,
[Your full name]
IIT Delhi, [programme], [entry number]
[phone]
