# FINN Plan 2 — Push Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the digest's material stories into the cards the brief asks for:
- results stories show Revenue / EBITDA / PBT / PAT with QoQ and YoY, with bank-aware metrics for banks and NBFCs;
- management-change stories show who is in and who is out, with a bio grounded in the filing;
- deal, rating, litigation and fund-raise stories get a one-line "why it matters" and key facts, every number checked against the source.

**Architecture:**
- **Results** come from NSE's integrated-filing XBRL, which is exact, structured and free. The results path uses no LLM, and every percentage is computed in Python.
- **People and briefs** come from the filing PDF's text. pypdf extracts it, the relevant passages are windowed under Groq's free-tier token limit, and one LLM call extracts structure. A grounding guard drops any name, sentence or number that is not in the source.
- **When it runs:** everything runs at refresh time and is stored in SQLite. The API stays read-only, because it is served from Vercel off a committed snapshot.
- **Fallbacks:** the LLM router gains cross-provider fallback chains, so one provider's outage does not block a refresh.

**Tech Stack:** Python 3.12+, uv, FastAPI, httpx, pydantic v2, SQLite, `xml.etree` (stdlib) for XBRL, `pypdf` (BSD) for PDF text, pytest + respx.

**Spec:** `docs/DESIGN.md` (the approved design), especially §1 "Today" card types, §2 model routing and "Arithmetic stays out of the LLM", and §7b "Banks/NBFCs get sector-aware metrics" and "Consolidated over standalone".

**Spike findings this plan relies on (2026-11-09, recorded as fixtures):**
- `GET https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=X&type=Integrated%20Filing-%20Financials` returns `{"data": [...]}`. There is one row per quarter and basis (`qe_Date` like `30-SEP-2026`, `consolidated` is `Consolidated`/`Standalone`, `broadcast_Date` like `07-Nov-2026 17:33:17`, `audited`, `xbrl`, `revised_Date`). It goes back to Mar 2025, which is 7 quarters for TATASTEEL. The older `corporates-financial-results` endpoint stops at Dec 2024 and is not used.
- **XBRL file names encode the format:**
  - `INTEGRATED_FILING_INDAS_…` is a regular company;
  - `INTEGRATED_FILING_NBFC_INDAS_…` is an NBFC;
  - `INTEGRATED_FILING_BANKING_…` is a bank.
- **Contexts:** the 3-month context is the segment-free `<xbrli:context>` whose period ends on `DateOfEndOfReportingPeriod`.
  - In the Q2 and Q4 files, `OneD` is the quarter and `FourD` is the year to date or full year.
  - The Q1 file has only `OneD`.
  - Always select by dates, never by id.
  - Values are in INR; divide by 1e7 for ₹ crore.
- **Cross-check against screener.in (TATASTEEL, Sep 2026 consolidated):**
  - Revenue 65,436.24 = screener "Sales" 65,436.
  - EBITDA (revenue − (Expenses − FinanceCosts − D&A)) 10,533.07 = screener "Operating Profit" 10,533.
  - PAT 3,699.59 = screener "Net Profit" 3,700.
  - Screener's PBT adds the share of associates (5,342.88 + 112.27 = 5,455).
- **Filing PDFs:** appointment filings carry a "Brief Profile" section (Voltas, `tests/fixtures/pdf/106850979.txt`). Results-day filings can be 29 pages / 88k chars with the management change buried inside (`106846758.txt`, M&M). That is over Groq's free limit of 8K tokens per minute, so the text must be windowed.

## Global Constraints

- Python ≥ 3.12, managed with uv. The only new runtime dependency allowed is `pypdf`. No AGPL packages (so not PyMuPDF).
- **The API never touches the network or an LLM at request time.** Fetching, extraction and LLM calls happen only in `scripts/refresh.py`. Route handlers read SQLite.
- **Arithmetic stays out of the LLM.** Every value, % change and margin is computed in Python from XBRL facts.
- **Money:** INR → ₹ crore is `value / 1e7`. Cards carry crore rounded to 2 decimals. % changes are rounded to 1 decimal and margin deltas to whole basis points, computed from unrounded values.
- **% change rule:** `None` if either value is `None` or the prior value is ≤ 0. There is never a division by zero and never a % across a sign change.
- **Fiscal labels:** Q1 = Apr–Jun, Q2 = Jul–Sep, Q3 = Oct–Dec, Q4 = Jan–Mar. FY is the calendar year of the March that ends it, as two digits. 2026-09-30 → "Q2 FY27", 2026-03-31 → "Q4 FY26".
- **Basis:**
  - Consolidated is preferred; standalone is the fallback.
  - The current, prior-quarter and year-ago figures in one card always share one basis, and the card states it.
  - When the same (period, basis) was filed more than once, the latest `broadcast_Date` wins.
- **Grounding:** every LLM-produced string shown to users must be traceable to the source text.
  - Person names must appear in it, ignoring case, whitespace and honorifics.
  - Profile sentences must appear verbatim after whitespace normalisation.
  - Every number token in a brief must appear in it, comparing digits only.
  - Ungrounded items are dropped, never "fixed".
- **Refresh stages never raise.** Per-symbol and per-filing failures go into the summary's `errors`, and the run carries on.
- **Tests run offline:** respx for HTTP, files under `backend/tests/fixtures/`, and a FakeRouter for LLMs. No live calls in pytest.
- **Secrets:** never read or print `backend/.env`.

## Review Focus

1. **Q4 and half-year files hold two duration contexts** (quarter and YTD/FY). The parser must pick the 3-month one by dates. Task 2 pins this with the Mar 2026 fixture.
2. **Loss-making or zero prior periods:** a % change across a sign change, or over zero, must be `None` with a plain note ("swung to a loss"). It must never be a huge or negative-base %. Task 3.
3. **Missing pieces:**
   - an element the taxonomy omits, such as D&A for a bank;
   - a company with only standalone filings;
   - a missing prior quarter.

   The card still renders with what exists; absent comparisons are `None`, with a note. Tasks 3 and 4.
4. **Scanned (image-only), corrupt or very large PDFs:** text comes back empty. Enrichment records "no text" and skips; nothing crashes, and the 25 MB byte cap holds. Tasks 6 and 7.
5. **An LLM that invents a person, a profile sentence or a number** is dropped by the grounding guard. The card shows less, never something false. Tasks 7 and 8, each with a fabricated-output test.

---

### Task 1: Cross-provider LLM fallback chains

**Files:**
- Modify: `backend/finn/config.py` (add `FALLBACKS`, `chain_for`; route `bio` to Groq)
- Modify: `backend/finn/llm/router.py`
- Test: `backend/tests/test_llm_router.py`

**Interfaces:**
- Consumes: `route_for(task, settings) -> (provider, model)`, `PROVIDERS`, `LLMRouter._request`.
- Produces:
  - `FALLBACKS: dict[str, list[tuple[str, str]]]`.
  - `chain_for(task: str, settings: Settings) -> list[tuple[str, str]]`: the primary from `route_for`, then that task's fallbacks, with duplicates removed and order kept.
  - `LLMRouter.complete_json(task, system, user, *, doc_hash="") -> dict`: same signature.
  - `LLMRouter.last_model: str | None`: `"provider/model"` of the model that answered the last call, cached or live.

Defaults:
- `ROUTES["bio"] = "groq"`; `finn_model_bio = "openai/gpt-oss-120b"`.
  - "bio" now means "extract the people from a filing's text". Groq's strict JSON is reliable, and the windowed input fits its free limit of 8K tokens per minute.
- `FALLBACKS`:
  - `classify`, `oneliner`, `bio` → `[("gemini", "gemini-3.5-flash-lite")]`.
  - `extract_pdf`, `reason` → `[("gemini", "gemini-3.5-flash-lite")]`.
  - `extract_transcript` → `[("groq", "openai/gpt-oss-120b")]`.

Behaviour of `complete_json`:
1. For each (provider, model) in the chain, in order, look up the cache key `sha256(f"{provider}|{model}|{system}|{user}|{doc_hash}")`, which is the Plan 1 key. The first hit is returned (and logged as cached, as today).
2. Otherwise try each model in order:
   - Skip a provider whose key is empty, recording `"missing <KEY_NAME>"`.
   - Call `_request` with `retries = MAX_RETRIES` for the last model in the chain and `1` for any model that still has a fallback after it, so a hanging primary costs at most 2 attempts before moving on.
   - Any `LLMError`, including invalid JSON and a non-object reply, moves to the next model.
   - Success caches under that model's key, sets `last_model`, and returns.
3. If every model's key is missing, raise `LLMError(f"missing {first_key_name}")`. This keeps the Plan 1 message, and `test_missing_key_raises_before_http` must still pass.
4. Otherwise, raise `LLMError("all models failed: groq/openai/gpt-oss-120b: HTTP 503; gemini/gemini-3.5-flash-lite: ...")`.

- [ ] **Step 1: Write failing tests** in `tests/test_llm_router.py`. Patch sleeps with the existing `no_sleep` fixture; respx routes `GROQ` and the `GEMINI` URL for `gemini-3.5-flash-lite`.
  - `test_chain_for_appends_fallbacks`: `chain_for("classify", s) == [("groq", "openai/gpt-oss-120b"), ("gemini", "gemini-3.5-flash-lite")]`.
  - `test_falls_back_to_gemini_on_groq_5xx`: Groq returns 503 every time and Gemini returns `{"a": 1}`. The result is `{"a": 1}`, Groq was called exactly 2 times (1 + 1 retry), and `router.last_model == "gemini/gemini-3.5-flash-lite"`.
  - `test_falls_back_on_invalid_json`: Groq returns content `"not json"` and Gemini returns `{"b": 2}`, so the result is `{"b": 2}`.
  - `test_missing_primary_key_goes_straight_to_fallback`: `Settings(groq_api_key="", gemini_api_key="m")`. Groq's route has zero calls and Gemini's has one.
  - `test_cached_fallback_answer_skips_http`: two identical calls where the first fell back. The second makes zero HTTP calls and still sets `last_model` to the Gemini model.
  - `test_all_models_fail_names_each`: both return 503. `LLMError` is raised and its message contains both `"groq/openai/gpt-oss-120b"` and `"gemini/gemini-3.5-flash-lite"`.
- [ ] **Step 2:** Run `uv run pytest tests/test_llm_router.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** `FALLBACKS`/`chain_for` in `finn/config.py` and the loop in `LLMRouter.complete_json`. `_request` gains a `retries: int` parameter, and its error message uses that count.
- [ ] **Step 4:** Run `uv run pytest -q`. Expected: all pass, including every Plan 1 router test unchanged. Run `uv run ruff check . && uv run ruff format --check .`.
- [ ] **Step 5: Commit** `feat(llm): cross-provider fallback chains with fast failover`.

---

### Task 2: NSE integrated-financials fetch and XBRL parser

**Files:**
- Modify: `backend/finn/ingest/nse.py`.
  - Factor the retry/warm-up loop of `fetch_announcements` into `_get(url, params) -> httpx.Response` and `_get_json(url, params, expect: type) -> object`.
  - Add `fetch_integrated_financials` and `fetch_bytes`.
- Create: `backend/finn/ingest/xbrl.py`
- Test: `backend/tests/test_xbrl.py`; extend `backend/tests/test_nse.py`

**Interfaces:**
- Produces, in `finn/ingest/nse.py`:
  - `INTEGRATED_URL = f"{BASE_URL}/api/integrated-filing-results"`.
  - `NSEClient.fetch_integrated_financials(symbol: str) -> list[dict]`:
    - params `index=equities`, `symbol`, `type="Integrated Filing- Financials"`;
    - returns `data`, the list;
    - raises `NSEUnavailable` after retries, or when the body is not a JSON object holding a `data` list.
  - `NSEClient.fetch_bytes(url: str, max_bytes: int = 25_000_000) -> bytes`:
    - non-200 after retries → `NSEUnavailable`;
    - `content-length` or the actual body over `max_bytes` → `NSEUnavailable("… exceeds …")`.
- Produces, in `finn/ingest/xbrl.py`:
  ```python
  XbrlFormat = Literal["indas", "nbfc", "bank"]
  Basis = Literal["consolidated", "standalone"]

  class XbrlError(Exception): ...

  class FinancialsFiling(BaseModel):      # one row of the integrated-filing list
      symbol: str
      period_end: date
      basis: Basis
      audited: bool | None
      filed_at: datetime                   # broadcast_Date, IST-aware
      xbrl_url: str
      format: XbrlFormat | None            # from detect_format(xbrl_url)

  class QuarterFinancials(BaseModel):
      symbol: str
      period_start: date
      period_end: date
      basis: Basis
      format: XbrlFormat
      audited: bool | None
      facts: dict[str, float]              # INR, numeric facts of the 3-month context only

  def detect_format(url: str) -> XbrlFormat | None   # "BANKING"→bank, "NBFC"→nbfc, "INDAS"→indas, else None
  def parse_filing_list(rows: list[dict]) -> list[FinancialsFiling]
  def parse_xbrl(xml: bytes, *, format_hint: XbrlFormat | None = None) -> QuarterFinancials
  ```

Parsing rules:
- **`parse_filing_list`:**
  - keeps only `type == "Integrated Filing- Financials"`;
  - skips any row whose dates, basis or URL don't parse, without raising;
  - for duplicate (period_end, basis), keeps the latest `filed_at`;
  - returns rows sorted by period_end descending, then basis.
- **`parse_xbrl`:**
  - The period end comes from the `DateOfEndOfReportingPeriod` fact. The quarter context is the segment-free, scenario-free duration context ending on that date that lasts 80–100 days.
  - `facts` holds every fact with `unitRef="INR"` in that context; the first occurrence wins.
  - `symbol` comes from the `Symbol` fact, basis from `NatureOfReportStandaloneConsolidated`, and audited from `WhetherResultsAreAuditedOrUnaudited` (`"Audited"` → True, `"Unaudited"` → False, else None).
  - `format` is `format_hint`, else a heuristic: `InterestExpended` present → bank; `ImpairmentOnFinancialInstruments` present → nbfc; otherwise indas.
  - Malformed XML, a missing period end, or no quarter context → `XbrlError`.

- [ ] **Step 1: Write failing tests** in `tests/test_xbrl.py`, using the files in `tests/fixtures/xbrl/` and `tests/fixtures/nse/integrated_TATASTEEL.json`.
  - `test_parse_tatasteel_q2`: parse `TATASTEEL_2026-09-30_cons.xml` with `format_hint="indas"`. Expect:
    - `period_start == date(2026,7,1)`, `period_end == date(2026,9,30)`;
    - `basis == "consolidated"`, `audited is False`;
    - `facts["RevenueFromOperations"] == 654362400000.0`;
    - `facts["ProfitLossForPeriod"] == 36995900000.0`.
  - `test_q4_file_picks_the_quarter_not_the_year`: `TATASTEEL_2026-03-31_cons.xml` gives `period_start == date(2026,1,1)` and `facts["RevenueFromOperations"] == 632701300000.0`.
  - `test_q1_file_with_single_context`: `TATASTEEL_2026-06-30_cons.xml` gives `period_start == date(2026,4,1)` and `facts["RevenueFromOperations"] == 607942900000.0`.
  - `test_bank_format_detected_by_elements`: `IDFCFIRSTB_2026-09-30_sa.xml` without a hint gives:
    - `format == "bank"`, `basis == "standalone"`;
    - `facts["InterestEarned"] == 119217500000.0`;
    - `facts["InterestExpended"] == 57373400000.0`.
  - `test_nbfc_format_detected_by_elements`: `BAJFINANCE_2026-09-30_sa.xml` gives `format == "nbfc"` and `facts["ImpairmentOnFinancialInstruments"] == 21305100000.0`.
  - `test_detect_format_from_url`:
    - `".../INTEGRATED_FILING_BANKING_1745436_24102026063930_WEB.xml"` → `"bank"`;
    - `".../INTEGRATED_FILING_NBFC_INDAS_1742038_19102026075842_WEB.xml"` → `"nbfc"`;
    - `".../INTEGRATED_FILING_INDAS_1755442_07112026053333_WEB.xml"` → `"indas"`;
    - `"https://x/y.xml"` → `None`.
  - `test_malformed_xml_raises_xbrlerror`: `b"<not xml"` raises `XbrlError`.
  - `test_missing_quarter_context_raises`: read the Sep 2026 fixture, change the `OneD` context's `<xbrli:startDate>` to `2026-04-01` with a string replace, and expect `XbrlError`.
  - `test_parse_filing_list`: the 14 fixture rows give 14 filings. The Sep 2026 consolidated one has:
    - `filed_at == datetime(2026,11,7,17,33,17,tzinfo=IST)`;
    - `format == "indas"`, `audited is False`.

    The first element's `period_end == date(2026,9,30)`.
  - `test_parse_filing_list_dedupes_revisions`: two copies of the Sep 2026 consolidated row with `broadcast_Date` an hour apart give one filing carrying the later `filed_at`.
  - `test_parse_filing_list_skips_malformed_rows`: a row with `qe_Date: "-"` is skipped and the rest are kept.
- [ ] **Step 2: Write failing tests** in `tests/test_nse.py`, with respx:
  - `test_fetch_integrated_financials_returns_data_list`;
  - `test_fetch_integrated_financials_rejects_non_object`, where a list body raises `NSEUnavailable`;
  - `test_fetch_bytes_rejects_oversize`, with `content-length: 30000000` and `max_bytes=25_000_000`;
  - `test_fetch_bytes_ok`.

  Existing announcement tests must still pass after the refactor.
- [ ] **Step 3: Implement** the code in `finn/ingest/nse.py` and `finn/ingest/xbrl.py`.
- [ ] **Step 4:** `uv run pytest -q`, then ruff check and format. Expected: all pass.
- [ ] **Step 5: Commit** `feat(ingest): NSE integrated-filing XBRL fetch and parser`.

---

### Task 3: Results card math

**Files:**
- Create: `backend/finn/enrich/__init__.py` (empty)
- Create: `backend/finn/enrich/results.py` (math only, this task)
- Modify: `backend/finn/models.py` (add `MetricRow`, `MarginRow`, `ResultsCard`)
- Test: `backend/tests/test_results.py`

**Interfaces:**
- Consumes: `QuarterFinancials`, `XbrlFormat` from Task 2.
- Produces, in `finn/models.py`:
  ```python
  class MetricRow(BaseModel):
      key: str            # "revenue", "ebitda", "pbt", "pat", "interest_earned", "nii", "ppop", "provisions", "impairment", "gnpa", "nnpa"
      label: str
      value: float | None # ₹ crore, 2 dp
      qoq_pct: float | None = None
      yoy_pct: float | None = None
      computed: bool = False   # derived by FINN, not a reported line

  class MarginRow(BaseModel):
      key: str            # "ebitda_margin", "pat_margin"
      label: str
      value_pct: float | None
      qoq_bps: int | None = None
      yoy_bps: int | None = None

  class ResultsCard(BaseModel):
      symbol: str
      period_end: date
      period_label: str          # "Q2 FY27"
      basis: Literal["consolidated", "standalone"]
      format: Literal["indas", "nbfc", "bank"]
      audited: bool | None
      compared_qoq: date | None  # period_end of the prior-quarter figures used, or None
      compared_yoy: date | None
      metrics: list[MetricRow]
      margins: list[MarginRow]
      notes: list[str]
      sources: list[str]         # XBRL URLs, current first
  ```
- Produces, in `finn/enrich/results.py`:
  - `quarter_label(period_end: date) -> str`;
  - `quarter_end_shift(period_end: date, quarters: int) -> date`: e.g. `(2026-09-30, -1)` → `2026-06-30` and `(2026-09-30, -4)` → `2025-09-30`;
  - `pct_change(cur: float | None, prev: float | None) -> float | None`;
  - `metrics_for(q: QuarterFinancials) -> dict[str, float | None]`, in ₹ crore, unrounded;
  - `build_card(cur, prev, year_ago, sources: list[str]) -> ResultsCard`, where `prev` and `year_ago` are `QuarterFinancials | None` and must share `cur.basis`; a mismatched basis is treated as `None`.

Metric definitions, from XBRL facts in INR / 1e7; a missing element gives `None`:

| format | rows in order (key: label = formula) | margins |
|---|---|---|
| indas | revenue: Revenue = `RevenueFromOperations`; ebitda: EBITDA = `RevenueFromOperations − (Expenses − FinanceCosts − DepreciationDepletionAndAmortisationExpense)` (computed); pbt: PBT = `ProfitBeforeTax`; pat: PAT = `ProfitLossForPeriod` | ebitda_margin = ebitda / revenue; pat_margin = pat / revenue |
| nbfc | revenue: Revenue = `RevenueFromOperations`; nii: Net interest income = `InterestEarned − FinanceCosts` (computed); impairment: Credit cost = `ImpairmentOnFinancialInstruments`; pbt; pat | pat_margin |
| bank | interest_earned: Interest earned = `InterestEarned`; nii: Net interest income = `InterestEarned − InterestExpended` (computed); ppop: Operating profit (pre-provision) = `OperatingProfitBeforeProvisionAndContingencies`; provisions: Provisions = `ProvisionsOtherThanTaxAndContingencies`; pbt = `ProfitLossFromOrdinaryActivitiesBeforeTax`; pat = `ProfitLossForThePeriod`; gnpa: Gross NPA = `GrossNonPerformingAssets`; nnpa: Net NPA = `NonPerformingAssets` | none |

Notes, plain English, in this order, each only when it applies:
- indas: "EBITDA is computed: revenue from operations minus operating expenses (excludes other income)."
- bank/nbfc: "Lenders are shown on net interest income and pre-provision profit; EBITDA does not apply."
- Exceptional item: when `ExceptionalItemsBeforeTax` (indas/nbfc) or `ExceptionalItems` (bank) is non-zero: "PBT includes an exceptional item of ₹{x:,.2f} cr."
- Associates and JVs: when `ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod` is non-zero: "PAT includes ₹{x:,.2f} cr share of associates and joint ventures."
- PAT sign change against the prior quarter or year: "PAT swung to a loss vs {label}." or "PAT turned positive vs {label}."
- Missing comparison: when prev or year_ago is None: "No {QoQ|YoY} comparison: {label} figures not on file."

- [ ] **Step 1: Write failing tests** in `tests/test_results.py`, loading fixtures through `parse_xbrl`.
  - `test_quarter_label`:
    - `date(2026,9,30)` → "Q2 FY27";
    - `date(2026,3,31)` → "Q4 FY26";
    - `date(2026,6,30)` → "Q1 FY27";
    - `date(2025,12,31)` → "Q3 FY26".
  - `test_quarter_end_shift`: `(2026-09-30, -1)` → `2026-06-30`; `(2026-09-30, -4)` → `2025-09-30`; `(2026-03-31, -1)` → `2025-12-31`.
  - `test_pct_change_rules`: `pct_change(110, 100) == 10.0`; `pct_change(5, -3) is None`; `pct_change(5, 0) is None`; `pct_change(None, 3) is None`.
  - `test_tatasteel_q2_card`: cur Sep 2026, prev Jun 2026, year-ago Sep 2025. Use `pytest.approx(…, abs=0.06)` for % values and `abs=0.01` for crore. Expect:
    - labels and basis: `period_label == "Q2 FY27"`, `basis == "consolidated"`;
    - revenue: value 65436.24, qoq 7.6, yoy 11.5;
    - ebitda: value 10533.07, computed True, qoq 13.7, yoy 18.4;
    - pbt: value 5342.88, qoq 42.8, yoy 28.1;
    - pat: value 3699.59, qoq 55.1, yoy 16.2;
    - margins: ebitda_margin value 16.1, qoq_bps 86, yoy_bps 94; pat_margin qoq_bps 173, yoy_bps 23;
    - notes: one contains "exceptional item of ₹348.68 cr", and one contains "₹112.27 cr share of associates".
  - `test_bank_card_idfc`: cur Sep 2026, prev Jun 2026, no year-ago. Expect:
    - `format == "bank"`, metric keys in order `["interest_earned","nii","ppop","provisions","pbt","pat","gnpa","nnpa"]`;
    - nii 6184.41 with qoq 3.5; pat 1044.60 with qoq −2.8; all `yoy_pct` None;
    - `compared_yoy is None`;
    - notes include "No YoY comparison" and the lenders note;
    - `margins == []`.
  - `test_nbfc_card_bajaj`: nii 12150.30; impairment 2130.51; pat 5536.10; no comparisons.
  - `test_missing_element_gives_none_row`: build a `QuarterFinancials` from the Sep fixture with `DepreciationDepletionAndAmortisationExpense` popped from `facts`. Then ebitda is None, the ebitda margin is None, and revenue is still 65436.24.
  - `test_sign_change_has_note_not_pct`: cur PAT positive, prev PAT negative (synthetic `QuarterFinancials`). pat `qoq_pct is None`, and the notes contain "PAT turned positive vs Q1 FY27".
  - `test_basis_mismatch_is_ignored`: a standalone prev with a consolidated cur gives `compared_qoq is None`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Round values to 2 dp, % to 1 dp and bps to int, only when building rows.
- [ ] **Step 4:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `feat(enrich): results card math (QoQ/YoY, margins, bank/NBFC metrics)`.

---

### Task 4: Store financials and the refresh ingest stage

**Files:**
- Modify: `backend/finn/db.py` (table and helpers)
- Modify: `backend/finn/enrich/results.py` (add `ingest_financials`, `card_for`)
- Test: `backend/tests/test_results_store.py`

**Interfaces:**
- Consumes: Task 2 (`NSEClient.fetch_integrated_financials`, `fetch_bytes`, `parse_filing_list`, `parse_xbrl`, `detect_format`) and Task 3 (`build_card`, `quarter_end_shift`).
- Produces, in `finn/db.py`:
  - schema `financials(symbol TEXT, period_end TEXT, basis TEXT, format TEXT, period_start TEXT, audited INTEGER, filed_at TEXT, xbrl_url TEXT, facts_json TEXT, PRIMARY KEY(symbol, period_end, basis))`;
  - `upsert_financials(conn, q: QuarterFinancials, filed_at: datetime, xbrl_url: str) -> None`;
  - `get_financials(conn, symbol, period_end: date, basis) -> tuple[QuarterFinancials, datetime, str] | None`, returning (q, filed_at, xbrl_url);
  - `stored_financials_urls(conn, symbol) -> set[str]`;
  - `latest_financials(conn, symbol) -> tuple[date, str, datetime] | None`, returning the (period_end, basis, filed_at) of the newest period, consolidated preferred.
- Produces, in `finn/enrich/results.py`:
  - `ingest_financials(conn, client, symbols: list[str], pause_s: float = 0.5) -> FinancialsResult`, where `FinancialsResult` is a dataclass with `fetched: int`, `skipped: int` and `failed: dict[str, str]`;
  - `card_for(conn, symbol: str, period_end: date | None = None) -> tuple[ResultsCard, datetime] | None`: the card and the current period's filed_at; with no period_end it uses the latest.

`ingest_financials`, per symbol (sleep `pause_s` between symbols, via a module-level `_sleep` that tests patch):
1. `parse_filing_list(client.fetch_integrated_financials(symbol))`; if empty → `failed[symbol] = "no financials filings"`.
2. P = newest period_end. Basis = consolidated if a consolidated filing exists for P, else standalone.
3. The targets are P, `quarter_end_shift(P, -1)` and `quarter_end_shift(P, -4)`, all on that basis. Each target filing is fetched only if its `xbrl_url` is not in `stored_financials_urls`; a URL already stored counts toward `skipped`.
4. `parse_xbrl(fetch_bytes(url), format_hint=filing.format)` → `upsert_financials`.
5. Any exception for a symbol → `failed[symbol] = f"{type(e).__name__}: {e}"`, and continue. An `XbrlError` on one target fails only that target, which is recorded in the same failed entry; the symbol's other targets still run.

- [ ] **Step 1: Write failing tests** with a `FakeNSE` class whose `fetch_integrated_financials` returns the fixture rows and whose `fetch_bytes` returns fixture XML by URL. Map the three TATASTEEL consolidated URLs from the list fixture to the three fixture files; any other URL raises `NSEUnavailable`. Tests:
  - `test_ingest_stores_current_prev_and_year_ago`: 3 rows stored for TATASTEEL (2026-09-30, 2026-06-30, 2025-09-30, all consolidated); `fetched == 3`.
  - `test_second_ingest_skips_stored_urls`: `fetched == 0`, `skipped == 3`, and no `fetch_bytes` calls.
  - `test_failing_symbol_does_not_stop_others`: the symbols are `["BROKEN", "TATASTEEL"]`, where BROKEN's list call raises `NSEUnavailable`. `"BROKEN" in failed` and TATASTEEL is stored.
  - `test_card_for_builds_from_store`: after ingest, `card_for(conn, "TATASTEEL")` returns a card with `period_label == "Q2 FY27"`, revenue `qoq_pct ≈ 7.6`, and filed_at 2026-11-07 17:33:17 IST.
  - `test_card_for_unknown_symbol_is_none`.
  - `test_ingest_falls_back_to_standalone`: a list with only standalone rows; the stored basis is `"standalone"`. Build the rows by editing copies of the fixture rows in the test.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `feat(enrich): store XBRL financials; refresh ingest stage`.

---

### Task 5: Results cards in the digest and API

**Files:**
- Modify: `backend/finn/models.py` (`Story.results: ResultsCard | None = None`)
- Modify: `backend/finn/digest.py` (attach cards)
- Modify: `backend/finn/api/main.py` (`GET /results/{symbol}`)
- Test: `backend/tests/test_digest_results.py`; extend `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `card_for(conn, symbol, period_end=None)` from Task 4.
- Produces:
  - `attach_results(conn, stories: list[Story]) -> None`, in `finn/digest.py`. It mutates `story.results`, called by `build_digest` on shown and routine stories.
  - `GET /results/{symbol}` → `ResultsCard`; 404 `{"detail": "no results on file"}` when there is none. The symbol is upper-cased.

Attach rule: a story gets the latest card for its symbol only when all three hold:
- `story.category == "results"`;
- `story.subtype` is not `"intimation"`;
- the card's filed_at is within 4 days of `story.headline.filing.filed_at`, either side.

Otherwise `results` stays `None`. The frontend then shows "numbers pending", so a stale quarter's numbers are never shown on a new story.

- [ ] **Step 1: Write failing tests.** In `test_digest_results.py`:
  - `test_results_story_gets_card`: ingest the TATASTEEL fixtures via `FakeNSE`, upsert a results filing dated 2026-11-07 13:06 IST, and build the digest over that day. The story has `results.period_label == "Q2 FY27"`.
  - `test_card_not_attached_when_dates_far_apart`: the same with the filing dated 2026-12-20, giving `results is None`.
  - `test_intimation_story_gets_no_card`.
  - `test_non_results_story_untouched`.

  In `test_api.py`:
  - `test_results_endpoint`: `/results/tatasteel` gives 200 with `period_label` "Q2 FY27".
  - `test_results_endpoint_404`.
  - `test_digest_story_serialises_results`: the JSON has `stories[0]["results"]["metrics"][0]["key"] == "revenue"`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `feat(api): results cards on digest stories and /results/{symbol}`.

---

### Task 6: Filing PDF text and relevance windows

**Files:**
- Modify: `backend/pyproject.toml` (run `uv add pypdf`)
- Create: `backend/finn/enrich/pdftext.py`
- Modify: `backend/finn/db.py` (`doc_text` table and helpers)
- Create: `backend/tests/fixtures/pdf/hello.pdf`
  - It must contain the text `FINN test PDF. Mr. Ramesh Iyer is appointed as Chief Financial Officer.`
  - Generate it once with a small script using pypdf's writer plus a content stream, or hand-write a minimal one-page PDF.
  - Commit only the PDF, and check that `extract_text` reads it.
- Test: `backend/tests/test_pdftext.py`

**Interfaces:**
- Produces, in `finn/enrich/pdftext.py`:
  - `extract_text(pdf: bytes) -> str`: pypdf; pages joined with `"\n"`; any pypdf error or non-PDF bytes → `""`; never raises.
  - `get_doc_text(conn, client, url: str, max_bytes: int = 25_000_000) -> str`:
    - cached by URL in `doc_text(url TEXT PRIMARY KEY, fetched_at TEXT, chars INTEGER, text TEXT)`;
    - a cached `""` is also a hit, so scanned PDFs are not re-downloaded every refresh;
    - `client.fetch_bytes` errors propagate as `NSEUnavailable` and are not cached, so a transient failure retries next refresh.
  - `relevant_window(text: str, terms: list[str], max_chars: int = 12_000) -> str`:
    - if `len(text) <= max_chars`, return the text unchanged;
    - otherwise split into lines; mark every line containing any term (case-insensitive); take lines [i − 8, i + 30] around each hit; merge overlaps; join the windows in document order with `"\n…\n"`; cut to `max_chars`;
    - no hits → `text[:max_chars]`.
- Produces, in `finn/db.py`: `get_doc_text_cached(conn, url) -> str | None` and `save_doc_text(conn, url, text) -> None`.

- [ ] **Step 1: Write failing tests.**
  - `test_extract_text_reads_pdf`: `hello.pdf` contains "Ramesh Iyer".
  - `test_extract_text_garbage_is_empty`: `b"not a pdf"` → `""`.
  - `test_window_keeps_short_text_whole`: the Voltas fixture text (9,938 chars) is returned unchanged.
  - `test_window_finds_buried_change`: the M&M fixture (88,116 chars) with terms `["appoint", "cease", "resign", "retire", "Senior Management", "Brief profile"]` gives a result of at most 12,000 chars that contains "Shuchi Suri" and "Chief Sales & Marketing Officer".
  - `test_window_no_hits_takes_head`.
  - `test_get_doc_text_caches`: a fake client counts calls; two calls give 1 fetch, and both return the same text.
  - `test_get_doc_text_caches_empty_result`: garbage bytes give `""`, the second call makes no fetch.
  - `test_get_doc_text_fetch_error_not_cached`: the client raises `NSEUnavailable` once and then succeeds; the second call returns text.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `feat(enrich): filing PDF text with caching and relevance windows`.

---

### Task 7: Who is in, who is out — grounded people extraction

**Files:**
- Create: `backend/finn/enrich/people.py`
- Create: `backend/finn/enrich/grounding.py` (shared with Task 8)
- Modify: `backend/finn/models.py` (`PersonChange`; `Story.people: list[PersonChange] = []`)
- Modify: `backend/finn/db.py` (`enrichments` table and helpers)
- Modify: `backend/finn/digest.py` (attach people)
- Test: `backend/tests/test_people.py`, `backend/tests/test_grounding.py`

**Interfaces:**
- Consumes: `get_doc_text`, `relevant_window` (Task 6); `LLMRouter.complete_json("bio", ...)` and `last_model` (Task 1); `db.get_filing`.
- Produces, in `finn/enrich/grounding.py`:
  - `normalize(s: str) -> str`: NFKC, curly quotes → straight, collapse whitespace, casefold.
  - `name_in_text(name: str, text: str) -> bool`: strips leading honorifics `Mr. Mrs. Ms. Dr. Shri Smt.`, then checks whether `normalize(name)` is in `normalize(text)`.
  - `grounded_sentences(passage: str, text: str, max_words: int) -> str | None`: splits the passage into sentences on `(?<=[.!?])\s+`; keeps those whose `normalize` form is a substring of `normalize(text)`; joins them; trims to whole sentences within `max_words`; returns `None` if nothing is kept.
  - `numbers_grounded(s: str, text: str) -> bool`: every number token in `s` (regex `\d[\d,]*(?:\.\d+)?`, commas removed) appears in the comma-free text. Pure year-like tokens 1900–2100 count only if they appear too.
- Produces, in `finn/models.py`:
  ```python
  class PersonChange(BaseModel):
      name: str
      role: str | None = None
      change: Literal["appointed", "resigned", "retired", "ceased", "redesignated", "other"]
      effective: str | None = None      # as written in the filing
      profile: str | None = None        # grounded sentences only, ≤ 90 words
      incoming: bool                    # change in {"appointed", "redesignated"}
      source_seq_id: str
  ```
- Produces, in `finn/db.py`:
  - schema `enrichments(seq_id TEXT, kind TEXT, payload_json TEXT, model TEXT, created_at TEXT, PRIMARY KEY(seq_id, kind))`;
  - `save_enrichment(conn, seq_id, kind, payload: dict, model: str | None) -> None`;
  - `get_enrichments(conn, seq_ids: list[str], kind: str) -> dict[str, dict]`;
  - `filings_missing_enrichment(conn, kind, categories: set[str], start: datetime) -> list[tuple[Filing, Classification]]`: filings filed at or after `start` whose stored category is in `categories` and which have no row of that `kind`. Task 8 scores them, so the classification comes back too.
- Produces, in `finn/enrich/people.py`:
  - `PEOPLE_TERMS: list[str]`: appoint, resign, retire, cessation, cease, designat, brief profile, annexure, director, officer, key managerial, senior management.
  - `SYSTEM_PROMPT: str`;
  - `extract_people(router, f: Filing, text: str) -> list[PersonChange]`;
  - `enrich_people(conn, client, router, since: datetime) -> EnrichResult`, where `EnrichResult` is a dataclass with `done`, `empty` and `failed: dict[str, str]`;
  - `attach_people(conn, stories: list[Story]) -> None`.

Behaviour:
- **`extract_people`:**
  - The user message is `f"SUBJECT: {f.subject}\n\nFILING TEXT:\n{relevant_window(text, PEOPLE_TERMS)}"`.
  - The reply schema is `{"people":[{"name","role","change","effective","profile"}]}`.
  - Validation:
    - drop people where `not name_in_text`;
    - an unknown `change` becomes `"other"`;
    - `profile = grounded_sentences(raw_profile, text, 90)`;
    - drop duplicates by normalized name.
- **`enrich_people`:**
  - Targets are management_change filings since `since` with no `"people"` enrichment.
  - text = `get_doc_text(pdf_url)` if `pdf_url` is set, else `nse_summary or ""`.
  - If the text is empty, save `{"people": [], "reason": "no text"}` and count it as `empty`.
  - An `LLMError` or `NSEUnavailable` goes to `failed[seq_id]` and nothing is saved, so the filing is retried next refresh.
  - Otherwise save `{"people": [...]}` with `model=router.last_model`.
- **`attach_people`:** for management_change stories, gather every member's saved people, dedupe by normalized name, and put incoming people first.

- [ ] **Step 1: Write failing grounding tests** in `test_grounding.py`:
  - `name_in_text("Mr. Jayant Balan", voltas_text)` is True; `name_in_text("John Doe", voltas_text)` is False.
  - On a passage of a real Voltas profile sentence plus `"He also won a Nobel Prize."`, `grounded_sentences` keeps only the first sentence.
  - `numbers_grounded("₹5,000 crore deal", "deal worth Rs 5000 crore")` is True; `numbers_grounded("₹6,000 crore", ...)` is False.
- [ ] **Step 2: Write failing people tests** in `test_people.py`, with a FakeRouter returning fixed JSON and `last_model = "groq/openai/gpt-oss-120b"`:
  - `test_extract_keeps_grounded_people`: on the Voltas text, a reply containing Jayant Balan (appointed, the real profile's first sentence), Noel N. Tata (retired) and "John Doe" (appointed) gives 2 people. John Doe is dropped; Balan has `incoming=True` and a profile starting "Mr. Jayant Balan is a Mechanical Engineer".
  - `test_fabricated_profile_sentence_dropped`.
  - `test_unknown_change_becomes_other`.
  - `test_enrich_saves_and_skips_next_time`: on the second run the router is called 0 times.
  - `test_no_text_saved_as_empty`.
  - `test_llm_error_not_saved`: the next run retries.
  - `test_digest_attaches_people_incoming_first`: two member filings, deduped, with the incoming person first.
- [ ] **Step 3:** Run. Expected: FAIL.
- [ ] **Step 4: Implement.** `SYSTEM_PROMPT` must:
  - ask for every person whose role changes;
  - define each `change` value;
  - ask for `profile` copied verbatim from the filing's brief profile, or `null`;
  - say "Use only the filing text; if unsure, omit the person."
- [ ] **Step 5:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 6: Commit** `feat(enrich): grounded people extraction for management changes`.

---

### Task 8: One-line briefs with number grounding

**Files:**
- Create: `backend/finn/enrich/brief.py`
- Modify: `backend/finn/models.py` (`Fact`, `Brief`; `Story.brief: Brief | None = None`)
- Modify: `backend/finn/digest.py` (attach briefs)
- Test: `backend/tests/test_brief.py`

**Interfaces:**
- Consumes: `grounding.normalize`, `numbers_grounded`; `get_doc_text`, `relevant_window`; `LLMRouter` task `"oneliner"`; `save_enrichment`/`get_enrichments`/`filings_missing_enrichment` (Task 7).
- Produces:
  ```python
  class Fact(BaseModel):
      label: str
      value: str

  class Brief(BaseModel):
      one_liner: str
      facts: list[Fact] = []
      quote: str | None = None
      by: Literal["llm", "nse_summary"]
      source_seq_id: str
  ```
- Produces, in `finn/enrich/brief.py`:
  - `BRIEF_CATEGORIES = {"mna", "fund_raise", "credit_rating", "litigation", "pledging", "capex", "insider_trading"}`;
  - `MIN_SCORE = 45`;
  - `make_brief(router, f: Filing, text: str) -> Brief | None`;
  - `enrich_briefs(conn, client, router, since: datetime, subscribed: set[str]) -> EnrichResult`, which targets filings in `BRIEF_CATEGORIES` whose `score_filing(...).score >= MIN_SCORE`;
  - `attach_briefs(conn, stories) -> None`, which gives each story the brief of its headline filing, else the brief of the first member that has one.

Validation in `make_brief`:
- The source is `f.subject + "\n" + (f.nse_summary or "") + "\n" + relevant_window(text, [category terms], 6000)`.
- **Reply:** `{"one_liner": str, "facts": [{"label","value"}], "quote": str|null}`.
- **One-liner:** it must be ≤ 30 words and pass `numbers_grounded` against the source.
- **Facts:** keep up to 3, each with a value that passes `numbers_grounded`.
- **Quote:** keep it only if its `normalize` form is a substring of the normalized source.
- **On LLM failure or an invalid one-liner:**
  - if `nse_summary` exists, return `Brief(one_liner=<its first sentence, ≤ 40 words>, by="nse_summary")`;
  - else return `None`.
- **Storage:** `enrich_briefs` saves `{"brief": {...}}`, or `{"brief": null, "reason": ...}`, under kind `"brief"`. A filing that fell back to the NSE summary is saved too, so it is not retried forever.

- [ ] **Step 1: Write failing tests:**
  - `test_grounded_brief_kept`: the source mentions "₹1,250 crore" and the reply's one-liner says "₹1,250 crore", so `by == "llm"`.
  - `test_invented_number_falls_back_to_summary`: the one-liner says "₹9,999 crore" and the NSE summary exists, so `by == "nse_summary"`.
  - `test_ungrounded_fact_dropped_grounded_fact_kept`.
  - `test_quote_not_in_source_dropped`.
  - `test_no_summary_and_bad_reply_gives_none`.
  - `test_only_material_categories_enriched`: a dividend filing is not sent to the router.
  - `test_digest_attaches_headline_brief`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.** The prompt asks for one plain-English sentence on why an investor should care. It says to use only the source's numbers and to copy the supporting quote verbatim.
- [ ] **Step 4:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `feat(enrich): grounded one-line briefs for material stories`.

---

### Task 9: Refresh orchestration, results eval, docs

**Files:**
- Modify: `backend/scripts/refresh.py`
- Create: `backend/finn/ingest/screener.py`
- Create: `backend/scripts/eval_results.py`
- Modify: `docs/EVALS.md`, `docs/DESIGN.md`
- Test: extend `backend/tests/test_refresh.py`; create `backend/tests/test_screener.py`, `backend/tests/test_eval_results.py`

**Interfaces:**
- Consumes: `ingest_financials` (Task 4), `enrich_people` (Task 7), `enrich_briefs` (Task 8), and the existing `refresh()` structure.
- Produces:
  - `refresh()` runs three new stages after classification, each wrapped like the existing ones so it can never raise:
    1. `"financials"`: `ingest_financials` for all portfolio symbols. It needs no LLM and runs with `--no-llm` too.
    2. `"people"`: `enrich_people(since=now − days)`. Skipped when the router is None.
    3. `"briefs"`: `enrich_briefs(since=now − days, subscribed=Rules().categories)`. Skipped when the router is None.
  - The summary gains `"financials": {"fetched","skipped","failed"}` and `"enrich": {"people": {...}, "briefs": {...}}`. Every failed entry is also appended to `errors` as `"financials: SYM: reason"` and similar.
  - `parse_quarters(html: str) -> dict[str, dict[str, float]]`, in `finn/ingest/screener.py`:
    - maps a column header (`"Sep 2026"`) to row label → value in ₹ crore;
    - row labels come from the first cell's text with the `+` buttons and whitespace stripped (`"Sales"`, `"Revenue"`, `"Operating Profit"`, `"Profit before tax"`, `"Net Profit"`, `"Interest"`, …);
    - `%` rows are skipped, and so is "Raw PDF";
    - `"1,234"` becomes 1234.0 and `""` is skipped.
  - `fetch_quarters(symbol, basis) -> str`: GET `https://www.screener.in/company/{symbol}/consolidated/` for consolidated, or `/company/{symbol}/` for standalone, with a browser User-Agent; returns HTML.
  - `scripts/eval_results.py [--offline]` compares each stored card's current period with screener's same-month column:

    | format | our value | screener row |
    |---|---|---|
    | indas | revenue | Sales |
    | indas | ebitda | Operating Profit |
    | indas | PBT plus share of associates/JVs | Profit before tax |
    | indas | pat | Net Profit |
    | bank | interest_earned | Revenue |
    | bank, nbfc | pbt | Profit before tax |
    | bank, nbfc | pat | Net Profit |
    | nbfc | revenue | Revenue |

    A pair matches when it is within 1% or ₹1 cr. The script prints a Markdown table with a per-metric match rate and the misses. `--offline` uses the TATASTEEL/IDFCFIRSTB/BAJFINANCE fixtures and builds cards from the XBRL fixtures; live mode uses `DB_PATH` and fetches screener.

- [ ] **Step 1: Write failing tests:**
  - `test_parse_quarters_tatasteel`: in the `"Sep 2026"` column, Sales == 65436.0, Operating Profit == 10533.0, Net Profit == 3700.0; `"Dec 2025"` is in the keys.
  - `test_parse_quarters_bank_rows`: IDFCFIRSTB `"Sep 2026"`: Revenue == 11923.0.
  - `test_eval_offline_tatasteel_all_match`: revenue, ebitda, pbt+assoc and pat all match within tolerance.
  - `test_refresh_runs_financials_without_llm`: use the existing refresh test doubles plus a FakeNSE for financials. With `use_llm=False`, `summary["financials"]["fetched"] == 3` and `"people" not in summary["enrich"]`.
  - `test_refresh_records_financials_failure_in_errors`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 5: Docs.**
  - `docs/DESIGN.md`:
    - replace the "Results-PDF number extraction | Gemini" routing row with "XBRL (deterministic, no LLM)";
    - change "Gold set: hand-label ~60 filings" to "Gold set: 104 filings (AI-labelled, see EVALS.md)";
    - add a "Hosting (2026-11-09)" note: Docker Spaces now need HF PRO, so the backend runs on Vercel Python functions (read-only API over the committed snapshot) and refresh runs out-of-band.
  - `docs/EVALS.md` gets a "## 2. Results numbers" section explaining the method and the offline result. The controller fills in the live result.
- [ ] **Step 6: Commit** `feat(refresh): financials, people and brief stages; results eval vs screener`.

---

## After the tasks (controller)

1. Live refresh into a scratch copy of the seed: `uv run python scripts/refresh.py --days 30 --out <scratch>`. Inspect the financials, people and briefs counts, plus a sample of each. Then install the seed.
2. Live `scripts/eval_results.py` over all 18 portfolio symbols, with the result recorded in `docs/EVALS.md`.
3. Render the 72-hour digest from the new seed and check by eye:
   - Tata Steel and Voltas results cards;
   - the Voltas people card, with Jayant Balan's profile;
   - CG Power's litigation brief.
