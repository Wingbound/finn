# FINN Plan 3 — Pull: Research Dossier and Promise Ledger

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user search any NSE ticker and get a dossier built only from the company's concall transcripts and annual report. The numbers come from filed financials. The dossier has five sections:
- the **Promise Ledger** (hero): management's last-4-quarter guidance, each item graded Kept, Partly, Missed, Pending or Quietly dropped, with the verbatim quote, source and page;
- a **Snapshot** of the business;
- the multi-year **Trajectory**;
- **Balance sheet and cash quality**, computed in Python;
- **Bull versus Bear** points.

Every LLM claim is cited, and anything the guard cannot verify is dropped.

**Architecture:**
- `finn/research/` builds a `Dossier` in stages, each reporting progress through a callback:
  1. screener (financial tables plus document index);
  2. PDFs (per-page text, cached);
  3. guidance extraction (one LLM call per transcript);
  4. the ledger (code-graded where the actuals exist, LLM-judged otherwise, with grounded evidence);
  5. synthesis (snapshot plus bull and bear).
- Dossiers are cached in SQLite.
- The demo set is precomputed by `scripts/research.py` into the committed snapshot.
- Unknown tickers build live through an SSE endpoint. This is the one request-time path allowed to use the network and LLMs, and it is capped well under Vercel's 300 s.

**Tech Stack:** Python 3.12+, uv, FastAPI (`StreamingResponse` for SSE), httpx, pydantic v2, SQLite, pypdf, the existing `LLMRouter`, and `finn/enrich/grounding.py`.

**Spec:** `docs/DESIGN.md`, sections:
- §1 "Research (Pull)" (sections, citation chips, grounding guard);
- §2 "Arithmetic stays out of the LLM" and model routing;
- §7b "Ledger window".

**Spike findings (2026-11-09, recorded as fixtures in `backend/tests/fixtures/research/`):**
- **Search:** `GET https://www.screener.in/api/company/search/?q=persistent` returns `[{"id": 2458, "name": "Persistent Systems Ltd", "url": "/company/PERSISTENT/consolidated/"}]`.
- **`PERSISTENT_screener.html`** is the company page's sections: `top-ratios`, `quarters`, `profit-loss`, `balance-sheet`, `cash-flow`, `ratios`, `documents`. Row labels:
  - **P&L:** `Sales`, `Expenses`, `Operating Profit`, `OPM %`, `Other Income`, `Interest`, `Depreciation`, `Profit before tax`, `Tax %`, `Net Profit`, `EPS in Rs`, `Dividend Payout %`. The columns are `Mar 2015` … `Mar 2026`, then `TTM`. After the table come separate growth tables ("10 Years:", and so on), which are ignored.
  - **Balance sheet:** `Equity Capital`, `Reserves`, `Borrowings`, `Other Liabilities`, `Total Liabilities`, `Fixed Assets`, `CWIP`, `Investments`, `Other Assets`, `Total Assets`. The last column may be a half-year (`Sep 2026`).
  - **Cash flow:** `Cash from Operating Activity`, `Cash from Investing Activity`, `Cash from Financing Activity`, `Net Cash Flow`, `Free Cash Flow`, and a `CFO/EBITDA` row whose label carries help text.
  - **Ratios:** `Debtor Days`, `Inventory Days`, `Days Payable`, `Cash Conversion Cycle`, `Working Capital Days`, `ROCE %`.
  - **Banks and NBFCs** use `Revenue`, `Interest`, `Financing Profit` and `Financing Margin %` in place of `Sales`, `Operating Profit` and `OPM %`; see the Plan 2 IDFCFIRSTB and BAJFINANCE fixtures.
- **Documents:**
  - concall rows match `<li class="flex flex-gap-8 flex-wrap-420">`;
  - the date is in `<div … style="width: 74px">Oct 2026</div>`;
  - a transcript is either `<a href=…>Transcript</a>`, or a plain `<div class="button-chip">Transcript</div>` while it is not yet posted;
  - annual reports are `<a href="…">Annual Report 2026</a>`.
- **BSE PDFs** download with a browser UA and `Referer: https://www.bseindia.com/`.
- **`PERSISTENT_transcripts.json`** holds `[{date, url, pages: [page text…]}]` for the Oct 2026, Aug 2026, Apr 2026 and Jan 2026 calls, 26–29 pages and 57–71k characters each. That is about 15k tokens per call: fine for Gemini Flash-Lite, too big for Groq's free 8K TPM.
- **Persistent says "we don't give forward looking guidance".** Its promises are qualitative or aspirational, so the ledger must grade qualitative claims as well as numeric targets.

## Global Constraints

- Python ≥ 3.12, uv. **No new dependencies.**
- **Primary sources only for narrative.**
  - Promises, evidence, snapshot and bull/bear text come only from concall transcripts and annual reports.
  - Numbers come from screener's tables, which restate filed financial statements, and from stored NSE XBRL.
  - screener's "About" text, pros/cons and analysis are never used.
- **Every LLM-written claim carries a citation:** `{source_id, page, quote}`, where the quote is verbatim in that page under `grounding.normalize`. If the quote is found on a different page of the same source, the page is corrected. A claim whose quote is not found anywhere in that source is dropped.
- **Arithmetic stays out of the LLM.** Growth, margins, D/E, CFO/PAT, CAGR and ledger "actual" values are computed in Python. The LLM may only choose a status where code cannot.
- **Request-time network and LLM** are allowed only for `GET /research/search` and `GET /research/{symbol}/build`. Every other route reads SQLite only.
- **Live-build budget:**
  - at most 4 transcripts;
  - at most 40 annual-report pages;
  - at most 12 LLM calls per dossier;
  - a 240 s soft deadline, after which remaining sections are skipped with a reason.
- **Stages never raise out of `build_dossier`.** A failed section is `null` with a plain-English `reason`, and the dossier still returns.
- **Tests run offline:** respx, fixtures, FakeRouter. No live calls.
- **Fiscal labels:** as in Plan 2 (Q2 FY27 = Jul–Sep 2026).
- A call's quarter is the latest quarter end before the call month starts. Oct and Nov 2026 calls are Q2 FY27; Jul and Aug are Q1; Apr and May are Q4 FY26; Jan and Feb are Q3.
- **Secrets:** never read or print `backend/.env`.

## Review Focus

1. **Few or no transcripts** (new listing, transcript not posted yet, or screener has no link). The dossier still builds, and the ledger says "Not enough concall transcripts on file (found N)" instead of failing. Tasks 3, 5 and 7.
2. **Banks and NBFCs on screener.** The trajectory uses `Revenue` and `Financing Profit`/`Financing Margin %`. EBITDA-specific flags are skipped, never crash, and never show nonsense. Task 2.
3. **Search misses or ambiguity.** An unknown query gives an empty list. `/research/{symbol}` for an unbuilt symbol gives 404 with a build link. A symbol screener doesn't know makes the SSE stream end with a clear `error` event. Tasks 1 and 7.
4. **Fuzzy promise horizons** ("this year", "next 2–3 quarters", "medium term", "FY27"). Unparseable horizons go to the judged path or Pending. They never crash, and they never produce a computed grade against the wrong period. Task 5.
5. **An LLM quote with the wrong page, or paraphrased.** A wrong page is corrected to where the quote actually is. A paraphrase is dropped, as is any ledger row or bull/bear point that depends on it. Tasks 4–6.

---

### Task 0: Plan 2 carry-overs

**Files:**
- Modify: `backend/finn/api/main.py`, `backend/finn/digest.py`, `backend/finn/llm/router.py`
- Test: `tests/test_api.py`, `tests/test_digest_results.py`, `tests/test_llm_router.py`

**Interfaces:**
- `GET /results/{symbol}` uses `digest._card_or_none` (rename it to the public `card_or_none`, updating the callers). A corrupt row gives 404 `{"detail": "no results on file"}`, never a 500.
- The router's `_exhausted_until` is keyed by `(provider, model)`, not provider. The error text is unchanged.
- In `attach_results`, a story gets the latest card when `-4 days ≤ story.headline.filing.filed_at − card_filed_at ≤ 45 days`, with the category and intimation rules unchanged. That is: from 4 days before the XBRL, to 45 days after.

- [ ] **Step 1: Write failing tests:**
  - `test_results_endpoint_corrupt_row_is_404`;
  - `test_quota_on_one_model_keeps_sibling_model_usable`: two Gemini models in a chain; the first returns a quota 429; the second is still called;
  - `test_same_quarter_story_45_days_later_gets_card`: a story 19 days after the card gets it;
  - `test_story_60_days_later_gets_no_card`;
  - update `test_card_not_attached_when_dates_far_apart`. Its story date 2026-12-20 is +43 days from the card (2026-11-07), which would now attach. Move the story date to 2027-01-15 (+69 days) and keep the assertion that no card is attached.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `fix: Plan 2 carry-overs (results 404 guard, per-model quota, same-quarter attach window)`.

---

### Task 1: screener company data — search, tables, documents

**Files:**
- Modify: `backend/finn/ingest/screener.py`
- Test: `backend/tests/test_screener.py`

**Interfaces** (all in `finn/ingest/screener.py`):
```python
SCREENER = "https://www.screener.in"
class ScreenerError(Exception): ...

def search(query: str, client: httpx.Client | None = None) -> list[dict]
    # [{"name": "Persistent Systems Ltd", "symbol": "PERSISTENT", "url": "/company/PERSISTENT/consolidated/"}]
    # symbol parsed from url "/company/<SYM>/..."; [] on no match; ScreenerError on HTTP failure
def fetch_company(symbol: str, client: httpx.Client | None = None) -> tuple[str, str]
    # (html, basis): try /company/{SYM}/consolidated/ then /company/{SYM}/ when the consolidated
    # page has no profit-loss data; ScreenerError if neither page exists (404) or has data
def parse_table(html: str, section_id: str, keep_pct: bool = True) -> dict[str, dict[str, float]]
    # column header -> row label -> value; generalises parse_quarters (which becomes
    # parse_table(html, "quarters", keep_pct=False)); "16%" -> 16.0 when keep_pct
def parse_documents(html: str) -> dict
    # {"annual_reports": [{"year": 2026, "url": ...}], "concalls": [{"date": "Oct 2026",
    #   "transcript_url": str | None, "ppt_url": str | None}]}, newest first, &amp; unescaped
def parse_name(html: str) -> str | None   # the <h1> text
```
- Label cleanup, as in Plan 2: strip tags, `&nbsp;`, `+` and whitespace. Additionally cut a label at the first run of 2+ spaces, so `"CFO/EBITDA       Share of…"` becomes `"CFO/EBITDA"`.
- Skip the "Raw PDF" row.
- Columns are the first table's `<thead>` cells, after the label column.

- [ ] **Step 1: Write failing tests** on `tests/fixtures/research/PERSISTENT_screener.html`:
  - `test_parse_profit_loss`: has `"Mar 2026"` and `"TTM"` columns, and `"Sales"`, `"Operating Profit"`, `"OPM %"` and `"Net Profit"` rows. Assert the Mar 2026 Sales value equals the fixture value: read the expected numbers from the fixture once while writing the test, and hard-code them.
  - `test_parse_balance_sheet_and_cash_flow_and_ratios`: `"Borrowings"`, `"Reserves"`, `"Free Cash Flow"`, `"CFO/EBITDA"` and `"Working Capital Days"` rows are present.
  - `test_parse_documents`: 4+ concalls with `transcript_url`; the first concall date is `"Oct 2026"`; at least one annual report with a `year`; no `&amp;` in any URL.
  - `test_parse_name`: contains "Persistent".
  - `test_search_parses_symbol`, with respx on `/api/company/search/` returning the spike JSON, gives `[{"name": "Persistent Systems Ltd", "symbol": "PERSISTENT", …}]`. An empty JSON list gives `[]`, and HTTP 500 gives `ScreenerError`.
  - `test_fetch_company_falls_back_to_standalone`, with respx: the consolidated page has no `id="profit-loss"` table rows, the standalone page has them, so the result is basis `"standalone"`.
  - The existing `parse_quarters` tests still pass.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(screener): search, company tables and document index`.

---

### Task 2: Deterministic financial analytics

**Files:**
- Create: `backend/finn/research/__init__.py` (empty), `backend/finn/research/financials.py`
- Modify: `backend/finn/models.py` (add `Trajectory`, `BalanceSheetHealth`, `Flag`)
- Test: `backend/tests/test_research_financials.py`

**Interfaces:**
```python
class Flag(BaseModel):
    level: Literal["good", "watch", "concern"]
    text: str                      # plain English, numbers formatted in

class Trajectory(BaseModel):
    years: list[str]               # last 5 fiscal-year columns ("Mar 2022" … "Mar 2026"), oldest first; TTM excluded
    revenue: list[float | None]    # ₹ cr: "Sales", or "Revenue" for lenders
    operating_profit: list[float | None]   # "Operating Profit", or "Financing Profit"
    margin_pct: list[float | None] # computed operating_profit / revenue × 100 (not screener's rounded OPM %)
    pat: list[float | None]        # "Net Profit"
    revenue_cagr_pct: float | None # over the span of available years (≥ 3 needed)
    pat_cagr_pct: float | None
    margin_change_bps: int | None  # last − first available
    read: Literal["growing", "compressing", "mixed", "insufficient data"]
    lender: bool

class BalanceSheetHealth(BaseModel):
    as_of: str                     # balance-sheet column used (latest fiscal year-end, not a half-year)
    debt_to_equity: float | None   # Borrowings / (Equity Capital + Reserves)
    cfo_to_pat_3y: float | None    # Σ CFO / Σ Net Profit over the last 3 fiscal years
    fcf_3y_cr: float | None        # Σ screener "Free Cash Flow", last 3 fiscal years
    working_capital_days: float | None
    wc_days_change_3y: float | None
    roce_pct: float | None
    flags: list[Flag]

def trajectory(pl: dict[str, dict[str, float]]) -> Trajectory
def balance_sheet_health(pl, bs, cf, ratios, lender: bool) -> BalanceSheetHealth
```
**Rules:**
- **CAGR:** `(last/first)^(1/n) − 1`, where n = years between them. `None` if first ≤ 0 or there are fewer than 3 points.
- **read:**
  - "growing" when revenue CAGR > 0 and margin change ≥ −100 bps;
  - "compressing" when margin change < −100 bps;
  - "mixed" otherwise;
  - "insufficient data" with fewer than 3 years.
- **Flags** (only those that apply):
  - D/E > 1.0 → concern "Debt is {x:.1f}× equity". D/E < 0.1 → good "Virtually debt-free (D/E {x:.2f})".
  - CFO/PAT 3y < 0.7 → concern "Only {x:.0%} of profit turned into operating cash over 3 years". ≥ 1.0 → good "Profits are backed by cash (CFO/PAT {x:.2f})".
  - WC days up by more than 15 over 3 years → watch "Working capital days rose from {a:.0f} to {b:.0f}".
  - FCF 3y < 0 → watch "Free cash flow was negative over 3 years (₹{x:,.0f} cr)".
- **Lenders:** the D/E, WC-days and FCF flags are skipped and those fields set to `None`; add one note flag: watch "Lender: leverage and working capital are judged on capital adequacy and asset quality, which this view does not cover".

- [ ] **Step 1: Write failing tests:**
  - On the PERSISTENT fixture tables (via Task 1's `parse_table`): exact `trajectory` values (5 years, revenue list, `margin_pct` computed, CAGR, read) and exact `balance_sheet_health` values. Compute the expected numbers by hand from the fixture once, and put them in the test with `pytest.approx(abs=0.01)`.
  - Lender: build `pl` from the Plan 2 `IDFCFIRSTB_consolidated_quarters.html`-style row labels ("Revenue", "Financing Profit"), using synthetic dicts. Then `lender=True`, `margin_pct` comes from Financing Profit, and the leverage flags are skipped.
  - Insufficient data: 2 years gives `read == "insufficient data"` and CAGR None.
  - Negative first value gives CAGR None.
  - Each flag's threshold is crossed in a synthetic case.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): deterministic trajectory and balance-sheet health`.

---

### Task 3: Sources — transcripts and annual report with per-page text

**Files:**
- Create: `backend/finn/research/docs.py`
- Modify: `backend/finn/db.py` (`doc_pages` table and helpers), `backend/finn/models.py` (`Source`)
- Test: `backend/tests/test_research_docs.py`

**Interfaces:**
```python
class Source(BaseModel):
    id: str                 # "T1" (newest transcript) … "T4", "AR"
    kind: Literal["transcript", "annual_report"]
    title: str              # "Q2 FY27 earnings call (Oct 2026)" | "Annual Report 2026"
    quarter: str | None     # "Q2 FY27" for transcripts
    url: str
    pages: list[str]        # page text; pages[0] is page 1

class DocClient:            # httpx wrapper: browser UA; Referer "https://www.bseindia.com/" for bseindia hosts
    def fetch_bytes(self, url: str, max_bytes: int = 40_000_000) -> bytes   # raises DocError
class DocError(Exception): ...

def call_quarter(date_label: str) -> str     # "Oct 2026" -> "Q2 FY27"; "Jan 2026" -> "Q3 FY26"; "May 2026" -> "Q4 FY26"
def pdf_pages(pdf: bytes, max_pages: int | None = None) -> list[str]   # pypdf, never raises ([] on failure)
def get_pages(conn, client: DocClient, url: str, max_pages: int | None = None) -> list[str]   # cached in doc_pages
def collect_sources(conn, client, documents: dict, max_transcripts: int = 4, ar_pages: int = 40,
                    progress: Callable[[str], None] = lambda m: None) -> tuple[list[Source], list[str]]
    # returns (sources, notes); newest transcripts first; skips a transcript that fails to download or has no
    # text, with a note ("Oct 2026 transcript unavailable: …"); the AR is the newest annual report, first ar_pages pages
```
- `doc_pages(url TEXT, page INTEGER, text TEXT, PRIMARY KEY(url, page))`.
- A cached document is all its pages. Store a sentinel row `page = 0` with `text = ""` when extraction gave no pages, so it is not re-downloaded.

- [ ] **Step 1: Write failing tests:**
  - `call_quarter` across all months;
  - `pdf_pages` on `tests/fixtures/pdf/hello.pdf` gives 1 page containing "Ramesh Iyer";
  - garbage bytes give `[]`;
  - `max_pages` is respected;
  - `get_pages` caches: a second call does not fetch, and the empty sentinel also prevents a refetch;
  - `collect_sources`:
    - pre-seed `doc_pages` from `PERSISTENT_transcripts.json` for the four transcript URLs, and use the Task 1 `parse_documents(PERSISTENT_screener.html)` output;
    - 4 transcript Sources with ids T1..T4, newest first;
    - T1's title is "Q2 FY27 earnings call (Oct 2026)", and its `pages` length matches the fixture;
    - the AR fetch fails via a fake client raising `DocError`, so the notes mention the annual report and no AR source is returned;
  - a concall with `transcript_url=None` is skipped silently (not posted yet);
  - with only 2 transcripts available, 2 Sources are returned and nothing crashes.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): transcript and annual-report sources with cached page text`.

---

### Task 4: Guidance extraction — grounded promises

**Files:**
- Create: `backend/finn/research/guidance.py`, `backend/finn/research/cite.py`
- Modify: `backend/finn/models.py` (`Citation`, `Promise`)
- Test: `backend/tests/test_research_guidance.py`, `backend/tests/test_research_cite.py`

**Interfaces:**
```python
class Citation(BaseModel):
    source_id: str
    page: int               # 1-based
    quote: str

class Promise(BaseModel):
    id: str                 # f"{source_id}-{n}"
    citation: Citation
    topic: str              # short, e.g. "revenue growth", "deal wins", "margin"
    kind: Literal["quantitative", "qualitative"]
    metric: Literal["revenue_growth", "ebitda_margin", "pat_growth", "capex", "order_book", "volume_growth", "other"] | None
    target_low: float | None
    target_high: float | None
    unit: Literal["%", "cr", "x", "usd_mn", "usd_bn"] | None
    horizon: str | None     # as said: "Q3 FY27", "FY27", "H2 FY27", "next year", None
    made_in: str            # the source's quarter, e.g. "Q2 FY27"

# cite.py
def locate(quote: str, source: Source, hint_page: int | None) -> Citation | None
    # verbatim (normalize) on hint page, else first page that contains it; None if nowhere or < 6 words
def tagged_text(source: Source, max_chars: int = 60_000) -> str   # "[[p1]]\n…\n[[p2]]\n…", truncated at a page boundary

# guidance.py
MAX_PROMISES = 8
def extract_promises(router, source: Source) -> list[Promise]
```
- **Prompt (router task `extract_transcript`):**
  - Extract up to 8 forward-looking statements by management: guidance, targets, plans and expectations.
  - Each item has a verbatim `quote` copied exactly, and the `page` from the `[[pN]]` markers.
  - Fill `metric`, `target_low`, `target_high` and `unit` only when the quote states a number.
  - Analyst questions are not promises.
  - Reply as JSON `{"promises": [...]}`.
- **Validation:**
  - Type-check every field.
  - The quote must `locate` (at least 6 words, verbatim); otherwise drop the item.
  - The page is corrected by `locate`.
  - A non-null target number must appear in the quote (`numbers_grounded(str(target), quote)`), else the targets are set to None and kind becomes "qualitative".
  - Unknown metric or unit values become None.
  - Dedupe by normalized quote.
  - An `LLMError` gives `[]`, and the caller records a note.

- [ ] **Step 1: Write failing tests:**
  - `locate`: finds a real sentence from fixture T1 page 3 when hinted with the wrong page (returns the right page); a paraphrase gives None; a 5-word quote gives None.
  - `tagged_text` keeps page markers and truncates at a page boundary.
  - `extract_promises` with a FakeRouter reply holding:
    - a real quote from the fixture with a wrong page (kept, page fixed);
    - an invented quote (dropped);
    - a quote with target 25 where the quote has no "25" (kept as qualitative with targets None);
    - a duplicate (deduped);
    - an analyst question (kept only if the LLM returns it; that cannot be tested, so skip);
    - non-string fields (no crash).
  - `LLMError` gives `[]`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): grounded guidance extraction from transcripts`.

---

### Task 5: Promise Ledger — computed where possible, judged with evidence otherwise

**Files:**
- Create: `backend/finn/research/ledger.py`
- Modify: `backend/finn/models.py` (`LedgerRow`, `Ledger`)
- Test: `backend/tests/test_research_ledger.py`

**Interfaces:**
```python
Status = Literal["kept", "partly", "missed", "pending", "dropped"]

class Actual(BaseModel):
    value: float
    unit: str
    period: str             # "Q2 FY27" | "FY26"
    basis: str              # e.g. "YoY revenue growth from screener quarterly table"

class LedgerRow(BaseModel):
    promise: Promise
    status: Status
    method: Literal["computed", "judged"]
    actual: Actual | None = None
    evidence: Citation | None = None   # from a LATER source than the promise
    rationale: str                     # one plain sentence

class Ledger(BaseModel):
    rows: list[LedgerRow]
    counts: dict[str, int]             # per status
    credibility_pct: float | None      # (kept + 0.5·partly) / (kept + partly + missed) × 100, None if 0 resolved
    note: str | None                   # e.g. "Not enough concall transcripts on file (found 1)"

def parse_horizon(horizon: str | None, made_in: str) -> tuple[Literal["quarter", "fy"], str] | None
    # "Q3 FY27" -> ("quarter","Q3 FY27"); "FY27"/"FY 2027"/"fiscal 2027" -> ("fy","FY27");
    # "next quarter" relative to made_in; anything else ("medium term", "H2", "next 2-3 years") -> None
def compute_status(p: Promise, quarters: dict, annual: dict) -> tuple[Status, Actual] | None
def build_ledger(router, promises: list[Promise], sources: list[Source], quarters: dict, annual: dict) -> Ledger
```
**Computed path.** Applies when `kind == "quantitative"`, metric is in {revenue_growth, ebitda_margin, pat_growth}, the unit is "%", and `parse_horizon` resolves to a period whose actuals exist in the screener tables. Quarter labels map to screener columns ("Q2 FY27" → "Sep 2026"; FY27 → "Mar 2027").
- **Growth:** YoY against the same column one year earlier. "Sales" or "Revenue", or "Net Profit".
- **Margin:** computed as operating profit / revenue × 100.
- **Grading** (lo = target_low, hi ignored for "at least" semantics):
  - growth: actual ≥ lo → kept; actual ≥ 0.8·lo → partly; else missed;
  - margin: actual ≥ lo → kept; actual ≥ lo − 1.0 → partly; else missed.
- A resolved horizon whose period has no actuals yet → `("pending", None)`.

**Judged path.** Everything else: qualitative, unparseable horizon, or other metrics.
- The router task is `reason`.
- Input: the promise, plus `relevant_window` excerpts of each LATER source (newer than `made_in`) for the promise's topic words, tagged with source id and page markers.
- Reply `{"status", "evidence_quote", "evidence_source", "evidence_page", "rationale"}`.
- **Evidence:** must `locate` in that later source. If it doesn't, the status becomes "pending" with rationale "No verifiable later evidence".
- **"dropped":** allowed only when there are ≥ 2 later sources and no evidence quote. Otherwise it becomes "pending".
- **No later source at all** → "pending", "Too recent to judge" without an LLM call.

**Budget and limits.**
- Judged rows are batched per promise source, so at most 4 calls. Each call judges all of that call's promises in one request: `{"judgements": [{"id", …}]}`.
- Promises from the newest source (T1) are always "pending" (no later source), so no call is made for them.
- With fewer than 2 transcripts, the ledger note becomes `f"Not enough concall transcripts on file (found {n})"`, while still returning rows.

- [ ] **Step 1: Write failing tests:**
  - `parse_horizon` table: the listed cases, plus "next quarter" from "Q2 FY27" giving "Q3 FY27".
  - `compute_status`, using synthetic screener tables:
    - kept, partly and missed for growth and for margin;
    - pending when the period column is missing;
    - None for a non-% unit.
  - `build_ledger` with FakeRouter, sources from the fixture (T1..T4) and synthetic promises:
    - (a) a computed row;
    - (b) a judged row whose evidence quote is real in a later source (kept, evidence page corrected);
    - (c) a judged row whose evidence quote is invented (becomes pending);
    - (d) "dropped" with only 1 later source (becomes pending);
    - (e) a T1 promise (pending, no LLM call);
    - (f) counts and `credibility_pct` exact;
    - (g) one source only (note set, no crash);
    - (h) the router called at most once per earlier source.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): Promise Ledger with computed and evidence-judged grades`.

---

### Task 6: Synthesis — snapshot and bull vs bear, all cited

**Files:**
- Create: `backend/finn/research/synthesis.py`
- Modify: `backend/finn/models.py` (`Snapshot`, `Point`)
- Test: `backend/tests/test_research_synthesis.py`

**Interfaces:**
```python
class Point(BaseModel):
    text: str               # ≤ 30 words
    citation: Citation

class Snapshot(BaseModel):
    summary: list[Point]    # 2–4 sentences about what the company does and its segments, each cited
def snapshot(router, sources: list[Source]) -> Snapshot | None
    # input: AR pages (if any) + T1's first 4 pages (management's opening remarks), tagged
def bull_bear(router, sources: list[Source], ledger: Ledger, trajectory: Trajectory, health: BalanceSheetHealth) -> tuple[list[Point], list[Point]]
    # input: ledger summary + flags + tagged excerpts; up to 3 each; ungrounded points dropped
```
- **Validation:** each point's quote must `locate` in its claimed source, or the point is dropped. The text must pass `numbers_grounded(text, quote + computed-facts string)`. Numbers may come from the quote or from the computed analytics, which are passed to the model as an explicit "FACTS" block that is also used for grounding.
- **Router task:** `reason`, one call each, so at most 2 calls.
- **On LLMError:** None / ([], []), with a note.

- [ ] **Step 1: Write failing tests:**
  - A FakeRouter snapshot with one real and one invented quote keeps only the real one.
  - A bull point with a number taken from the FACTS block is kept.
  - A bull point with an invented number is dropped.
  - A cap of 3 each.
  - An `LLMError` gives None and empty lists.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): cited snapshot and bull/bear`.

---

### Task 7: Dossier pipeline, storage, API with SSE, and CLI

**Files:**
- Create: `backend/finn/research/pipeline.py`, `backend/scripts/research.py`
- Modify: `backend/finn/db.py` (`dossiers` table), `backend/finn/models.py` (`Dossier`), `backend/finn/api/main.py`
- Test: `backend/tests/test_research_pipeline.py`, `backend/tests/test_api_research.py`

**Interfaces:**
```python
class Dossier(BaseModel):
    symbol: str
    name: str | None
    basis: str
    built_at: datetime
    sources: list[Source]   # API responses omit `pages` (see below)
    ledger: Ledger | None
    snapshot: Snapshot | None
    trajectory: Trajectory | None
    health: BalanceSheetHealth | None
    bull: list[Point]
    bear: list[Point]
    notes: list[str]        # every skipped/failed section with its reason
    cost: dict              # router.stats() delta: calls, cached, input_tokens, output_tokens, usd_list_price
    build_seconds: float

def build_dossier(conn, symbol: str, router, *, screener_client=None, doc_client=None,
                  progress: Callable[[str], None] = lambda m: None, deadline_s: float = 240) -> Dossier
```
- **Tables:** `dossiers(symbol TEXT PRIMARY KEY, built_at TEXT, payload_json TEXT)` with `save_dossier`, `get_dossier` and `list_dossiers`. Store the dossier **with** source pages, because citation excerpts are served from it.
- **API:**
  - `GET /research` → `[{symbol, name, built_at, counts}]`, read-only.
  - `GET /research/search?q=` → screener search (network allowed). Empty q gives 422.
  - `GET /research/{symbol}` → the cached dossier without source `pages`, or 404 `{"detail": "not built", "build": "/research/{SYM}/build"}`.
  - `GET /research/{symbol}/source/{source_id}/{page}` → `{title, page, text}` for citation chips, read-only, 404 if absent.
  - `GET /research/{symbol}/build` → `text/event-stream`. It emits `event: progress` with `data: {"msg": …}` for each progress message, then `event: done` with the dossier JSON (minus pages), or `event: error` with `{"detail": …}`. The built dossier is saved. A build that finishes within 10 minutes of a cached `built_at` is not re-run; the cached one streams immediately.
- **CLI:** `scripts/research.py SYM [SYM…] [--out DB]` builds and saves each dossier and prints a one-line summary per symbol (row counts, cost, seconds). It exits 0.
- **Progress messages, in order:** "Resolving {SYM} on screener", "Found {n} transcripts and {m} annual report(s)", "Reading {title}" (per source), "Extracting guidance from {title}", "Checking delivery on {k} promises", "Writing snapshot and bull/bear", "Done in {s:.0f}s".

- [ ] **Step 1: Write failing tests:**
  - `build_dossier` end to end, offline:
    - a fake screener client returns `PERSISTENT_screener.html`;
    - `doc_pages` is pre-seeded from the transcripts fixture, and a fake DocClient makes the AR fail;
    - a FakeRouter with a callable reply per task returns real quotes from the fixture;
    - the dossier has 4 sources, a ledger with rows, a trajectory, health and notes mentioning the annual report;
    - the progress messages come in order;
    - the cost dict is present.
  - A deadline of 0 s skips the LLM sections with a note, and the dossier still has its trajectory and health.
  - An unknown symbol (the screener client raises `ScreenerError`) raises `ScreenerError` from `build_dossier`. This is the one error that does propagate, so the API can say "not found".
  - API (TestClient):
    - list;
    - get 404 with the build link;
    - get 200 after save, without `pages`;
    - source page 200 and 404;
    - SSE build with monkeypatched `build_dossier` and progress gives `progress` events then `done`;
    - SSE build for an unknown symbol gives an `error` event;
    - search with q empty gives 422.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.** SSE uses `StreamingResponse` over a generator. Run `build_dossier` in a thread with a `queue.Queue` for progress messages, and yield them as they arrive.
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): dossier pipeline, cache, SSE build endpoint and CLI`.

---

### Task 8: Research eval and docs

**Files:**
- Create: `backend/scripts/eval_research.py`
- Modify: `docs/EVALS.md` (§4 "Research dossiers"), `docs/DESIGN.md`
- Test: `backend/tests/test_eval_research.py`

**Interfaces:** `scripts/eval_research.py [--db PATH]`. For every stored dossier it reports:
- (a) citation verification: re-`locate` every citation in the dossier against its stored source pages. Expect 100%; anything less is a bug, so list the failures;
- (b) the ledger status distribution, and computed versus judged counts;
- (c) the guard drop rate: promises proposed versus kept. This requires `build_dossier` to record in `notes` or `cost`, as `{"promises_proposed": n, "promises_kept": k, "points_proposed": …, "points_kept": …}`. Add a `guard` dict to `Dossier`.
- (d) cost and seconds.

It prints a Markdown table and exits 0.

- [ ] **Step 1: Write failing tests:** the eval on a dossier saved by the Task 7 offline test reports 100% citation verification. A deliberately corrupted citation in a saved dossier is reported as a failure.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement**, including the `Dossier.guard` field and its population in `build_dossier`, plus a test.
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Docs.**
  - `docs/EVALS.md` gets "## 4. Research dossiers": method, plus a placeholder "Live results: pending (controller)".
  - `docs/DESIGN.md`: the Pull section notes the request-time exception (search and build only), the live-build budget, and the ledger grading rules (computed thresholds; evidence-judged otherwise).
- [ ] **Step 6: Commit** `feat(research): dossier eval (citation verification, guard drop rate) and docs`.

---

## After the tasks (controller)

1. **Choose the demo set.** 3–5 companies, at least 2 outside the portfolio, each with ≥ 4 transcripts with links, at least one with numeric guidance, and ideally one with visible misses. Build them live into a scratch seed with `scripts/research.py`.
2. **Generalisation.** Build 3 random NSE tickers not in either set.
3. **Eval.** Run `scripts/eval_research.py`, then fill in EVALS §4.
4. **Seed.** Install it; the final review runs before the merge.
