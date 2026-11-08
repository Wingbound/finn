# Plan 1 — Backend foundation + Push backbone

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested FastAPI backend that ingests real NSE filings and EOD prices for an 18-stock portfolio, classifies and scores every filing, clusters them into stories, and serves a windowed digest, portfolio view and threshold alerts.

**Architecture:** Python package `finn` in `backend/`. Ingest writes to SQLite. Classification is persisted. Scoring, clustering and alerts are computed per request from client-supplied preferences, so the server holds no user state. The LLM router is introduced here: Groq handles only the filings the rules can't classify, and every call is cached and cost-logged.

**Tech Stack:** Python ≥3.12, uv, FastAPI, httpx, pydantic v2, pydantic-settings, yfinance, PyYAML, pytest, respx.

**Spec:** `docs/DESIGN.md` (with `docs/PROJECT_BRIEF.md` §4–5 for data findings and taxonomy). Later plans: Plan 2 push enrichment (results numbers, people bios, one-liners) · Plan 3 pull engine · Plan 4 frontend · Plan 5 deploy + submission.

## Global Constraints

- `requires-python = ">=3.12"`; all commands run from `backend/` via `uv run`.
- Timestamps: timezone-aware, Asia/Kolkata (IST, +05:30). Stored as ISO-8601 strings. Windows are computed in IST.
- Category names exactly: `results, mna, fund_raise, management_change, litigation, insider_trading, earnings_call, investor_meetings, credit_rating, dividend, bonus_split, capex, press_release, postal_ballot, agm_egm, pledging, unclassified` (`mna` displays as "M&A").
- Base scores: results 90 · mna 85 · management_change 80 · pledging 75 · litigation 75 · credit_rating 70 · fund_raise 70 · capex 60 · insider_trading 50 · bonus_split 40 · press_release 35 · earnings_call 30 · dividend 30 · agm_egm 15 · postal_ballot 15 · investor_meetings 10 · unclassified 5.
- Tiers: `critical` ≥ 75, `important` ≥ 45, else `routine`; noise filings get tier `noise` and score 0.
- Default alert rules: volume multiple **2.0×** the trailing **20**-session average volume; price move **±5.0%** close-to-close.
- No arithmetic is delegated to an LLM. Every LLM output is validated by a pydantic model, and invalid output falls back to a safe default instead of raising.
- Model IDs are never hard-coded from memory. They are chosen from the providers' list-models endpoints at implementation time and recorded in `finn/config.py` with the date checked.
- Secrets come only from env / `backend/.env` (gitignored); `backend/.env.example` is committed.
- Every outbound HTTP call has a timeout (30 s), browser-like `User-Agent`, and for NSE `Referer: https://www.nseindia.com/`.
- Portfolio (exactly these 18 NSE symbols): `RELIANCE PERSISTENT TECHM ZYDUSLIFE SUNPHARMA VOLTAS M&M TVSMOTOR ULTRACEMCO TRENT TATASTEEL MAXHEALTH IDFCFIRSTB BAJFINANCE CGPOWER AMBER LODHA PREMIERENE`.

## Review Focus

1. **NSE answers with HTML/403 or an empty body instead of JSON** (blocked IP, stale cookies). Expected behaviour: re-warm the session and retry with backoff, then raise `NSEUnavailable`. Already-stored data stays untouched and `as_of` doesn't advance. → Task 3 tests `test_retry_then_success` and `test_persistent_403_raises`.
2. **Partial or special sessions and today's in-progress bar.** Diwali Muhurat trading on Sun 8 Nov 2026 shows up as a tiny-volume bar, and during market hours Yahoo returns a live bar. Neither may trigger or skew alerts. → Task 8 tests `test_muhurat_bar_excluded`, `test_inprogress_bar_dropped`.
3. **Duplicate-looking filings.** NSE posted RELIANCE's 30-Oct "Outcome of Board Meeting" twice with the same subject and timestamp but *different PDFs*, and both must be kept. They must render as one story whose members include both, never as two cards. → Task 7 test `test_same_subject_filings_one_story`.
4. **Empty windows** (weekend or holiday, 0 filings). The digest must return zero counts and empty lists, not an error. → Task 9 test `test_digest_empty_window`.
5. **Symbols with special characters** (`M&M`, `BAJAJ-AUTO`). These must be URL-encoded for NSE, and their Yahoo symbol is `M&M.NS`. → Task 3 test `test_symbol_with_ampersand_encoded`, Task 1 test `test_yahoo_symbols`.
6. **LLM returns malformed JSON or an unknown category.** Expected: classification falls back to `unclassified` with `by="default"` and the batch keeps going. → Task 6 test `test_bad_llm_output_defaults`.

---

### Task 1: Scaffold, settings, portfolio

**Files:**
- Create: `backend/pyproject.toml`, `backend/.env.example`, `backend/finn/__init__.py`, `backend/finn/config.py`, `backend/finn/portfolio.yaml`, `backend/finn/portfolio.py`
- Test: `backend/tests/test_portfolio.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings; fields `gemini_api_key: str = ""`, `groq_api_key: str = ""`, `data_dir: Path = Path("data")`, `db_path: Path = data_dir/"finn.sqlite"`, `allowed_origins: list[str] = ["*"]`), `get_settings() -> Settings` (lru_cached). `Holding(symbol: str, name: str, sector: str, size: Literal["mega","large","mid","small"], yahoo: str)`, `load_portfolio(path: Path | None = None) -> list[Holding]`.

- [ ] **Step 1:** `uv init --package --name finn` in `backend/`. Add deps: `fastapi uvicorn[standard] httpx pydantic pydantic-settings yfinance pyyaml`. Add dev deps: `pytest respx ruff`. `.env.example` lists `GEMINI_API_KEY=` and `GROQ_API_KEY=`.
- [ ] **Step 2: Write failing tests.**
```python
def test_portfolio_has_18_unique():
    p = load_portfolio(); syms = [h.symbol for h in p]
    assert len(p) == 18 and len(set(syms)) == 18
def test_yahoo_symbols():
    p = {h.symbol: h for h in load_portfolio()}
    assert p["M&M"].yahoo == "M&M.NS" and all(h.yahoo.endswith(".NS") for h in p.values())
def test_sector_and_size_mix():
    p = load_portfolio()
    assert len({h.sector for h in p}) >= 10 and {"mega","large","mid","small"} <= {h.size for h in p}
```
- [ ] **Step 3:** Run `uv run pytest tests/test_portfolio.py -v` and confirm it FAILS.
- [ ] **Step 4:** Write `portfolio.yaml` (the 18 symbols from Global Constraints, each with `name, sector, size`; `yahoo` derived as `symbol + ".NS"` unless overridden) and `portfolio.py`. AMBER is `small`; the mega-caps are RELIANCE, SUNPHARMA, M&M, ULTRACEMCO and BAJFINANCE.
- [ ] **Step 5:** Run the tests and confirm they PASS. Commit `feat(backend): scaffold, settings, portfolio`.

### Task 2: Models and SQLite store

**Files:**
- Create: `backend/finn/models.py`, `backend/finn/db.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Produces (models): `Category` (Literal of the 17 names); `Filing(seq_id: str, symbol: str, company: str, nse_desc: str, subject: str, nse_summary: str | None, pdf_url: str | None, filed_at: datetime, has_xbrl: bool)`; `Classification(category: Category, subtype: str | None = None, noise: bool = False, by: Literal["rules","llm","default"], confidence: float)`; `PriceBar(symbol: str, date: date, open: float, high: float, low: float, close: float, volume: int)`.
- Produces (db): `connect(path: Path) -> sqlite3.Connection` (WAL, Row factory, creates parent dir); `init_db(conn) -> None`; `upsert_filings(conn, filings: list[Filing]) -> int` (returns number newly inserted; never overwrites a stored classification); `save_classifications(conn, items: dict[str, Classification]) -> None`; `unclassified_filings(conn) -> list[Filing]`; `filings_in_window(conn, symbols: list[str], start: datetime, end: datetime) -> list[tuple[Filing, Classification | None]]` (newest first); `upsert_prices(conn, bars: list[PriceBar]) -> int`; `price_history(conn, symbol: str, limit: int = 60) -> list[PriceBar]` (ascending by date); `set_meta(conn, key: str, value: str)`, `get_meta(conn, key: str) -> str | None`. Tables: `filings`, `prices`, `meta`, plus `llm_cache` and `llm_calls`, which Task 5 uses (create them here).

- [ ] **Step 1: Write failing tests:** `test_upsert_is_idempotent` (insert the same 3 filings twice: returns 3 then 0), `test_classification_survives_reupsert`, `test_window_filters_symbol_and_time` (a filing at 23:59 IST on the end date is included; one at 00:00 IST the next day is excluded), `test_price_history_ascending_and_limited`, `test_meta_roundtrip`. All use `tmp_path`.
- [ ] **Step 2:** Run them and confirm they FAIL.
- [ ] **Step 3:** Implement `models.py` and `db.py` per the interfaces, using plain `sqlite3` (no ORM). Store `filed_at` as an ISO string with offset, so lexicographic order equals time order within IST.
- [ ] **Step 4:** Run them and confirm they PASS. Commit `feat(backend): models and sqlite store`.

### Task 3: NSE announcements client and ingest

**Files:**
- Create: `backend/finn/ingest/__init__.py`, `backend/finn/ingest/nse.py`, `backend/scripts/record_fixtures.py`
- Create fixtures: `backend/tests/fixtures/nse/RELIANCE.json`, `M&M.json`, `TRENT.json` (real responses, 08-10-2026 → 08-11-2026), `backend/tests/fixtures/nse/portfolio_month.json` (all 18 symbols, same window)
- Test: `backend/tests/test_nse.py`

**Interfaces:**
- Consumes: `Filing`, `upsert_filings`, `set_meta` (Task 2).
- Produces: `class NSEUnavailable(Exception)`; `class NSEClient(timeout: float = 30, max_retries: int = 3)` with `fetch_announcements(symbol: str | None, start: date, end: date) -> list[dict]`; `parse_announcement(raw: dict) -> Filing`; `ingest_filings(conn, client: NSEClient, symbols: list[str], start: date, end: date) -> int` (sets meta `filings_as_of` only when every symbol succeeded).
- Endpoint: `GET https://www.nseindia.com/api/corporate-announcements` with params `index=equities`, `symbol` (when given), `from_date`/`to_date` as `DD-MM-YYYY`. Warm-up: `GET https://www.nseindia.com/` (ignore its 403) to collect cookies; re-warm on 401/403.
- Field mapping: `seq_id←seq_id`, `symbol←symbol`, `company←sm_name`, `nse_desc←desc`, `subject←attchmntText`, `nse_summary←voiceSummary`, `pdf_url←attchmntFile`, `filed_at←an_dt` (format `%d-%b-%Y %H:%M:%S`, IST), `has_xbrl←hasXbrl`.

- [ ] **Step 1:** Write `scripts/record_fixtures.py` (a real network call using `NSEClient` once it exists; until then plain httpx with the same headers). Run it, check the 4 fixture files are non-empty JSON lists, and commit them.
- [ ] **Step 2: Write failing tests:**
  - `test_parse_announcement_fields`: first RELIANCE fixture item has symbol `RELIANCE`, an aware `filed_at` with `utcoffset() == timedelta(hours=5, minutes=30)`, and a `pdf_url` starting `https://nsearchives.nseindia.com/`.
  - `test_retry_then_success`: respx returns 403 HTML twice, then fixture JSON. Expect the list returned and 3 API requests made.
  - `test_persistent_403_raises`: expect `NSEUnavailable`; after `ingest_filings`, the DB is unchanged and `get_meta("filings_as_of") is None`.
  - `test_symbol_with_ampersand_encoded`: the request URL contains `symbol=M%26M`.
  - `test_ingest_counts_new_only`: ingest the fixture twice; the second call returns 0.
- [ ] **Step 3:** Run them and confirm they FAIL.
- [ ] **Step 4:** Implement `nse.py`. Use exponential backoff (0.5 s, 1 s, 2 s; patched to 0 in tests). A non-JSON body or a `content-type` other than JSON counts as a failure.
- [ ] **Step 5:** Run them and confirm they PASS. Commit `feat(ingest): NSE announcements client with retry and ingest`.

### Task 4: Rule-based classifier

**Files:**
- Create: `backend/finn/classify/__init__.py`, `backend/finn/classify/rules.py`
- Test: `backend/tests/test_rules.py`

**Interfaces:**
- Consumes: `Filing`, `Classification`.
- Produces: `classify_rules(f: Filing) -> Classification | None` (None means "ambiguous, send to LLM"); `NOISE_DESCS: frozenset[str]`; `DESC_MAP: dict[str, tuple[Category, str | None]]`.

Decisions the implementer can't infer:
- **Noise** (`noise=True`, category `unclassified`): `Copy of Newspaper Publication`, `Loss of Share Certificates`, `Loss of share certificate`, `Issue of Duplicate Share Certificate`, `Certificate under SEBI (Depositories and Participants) Regulations, 2018`, `Trading Window`, `Structural Digital Database`, `Registrar & Share Transfer Agent Update`, `Address Change`, `Quarterly Compliance Report on Corporate governance - within 21 days from the end of the quarter`, `Integrated Filing- Governance`.
- **Unambiguous `DESC_MAP`** (desc → category, subtype):
  - `Acquisition` → mna/acquisition; `Amalgamation/Merger` → mna/merger; `Scheme of Arrangement` → mna/scheme; `Demerger` → mna/demerger; `Sale or disposal` → mna/divestment; `Diversification/Disinvestment` → mna/divestment; `Open Offer` and `Public Announcement-Open Offer` → mna/open_offer.
  - `Appointment`, `Change in Management`, `Change in Director(s)`, `Resignation of Director/KMP/SMP`, `Resignation`, `Cessation`, `Retirement`, `Demise`, `Change in Company Secretary/Compliance Officer` → management_change (subtype from the role regex below).
  - `Credit Rating`, `Credit Rating- New`, `Credit Rating- Revision`, `Credit Rating- Others` → credit_rating (subtype from the text regex: `upgrad` → upgrade, `downgrad` → downgrade, `reaffirm` → reaffirm, `- New` → new).
  - `Action(s) taken or orders passed`, `Action(s) initiated or orders passed`, `Pendency of Litigation(s)/dispute(s) or the outcome impacting the Company`, `Corporate Insolvency Resolution Process`, `Fraud/Default/Arrest`, `Initiation of Forensic Audit`, `Final  forensic  audit  report`, `Defaults on Payment of Interest/Principal` → litigation.
  - `Qualified Institutional Placement`, `Rights Issue`, `Preferential issue`, `Issue of Securities`, `Buyback`, `Public Announcement - Buyback of Shares`, `Post Buyback Public Announcement`, `Closure of Buy Back` → fund_raise.
  - `Allotment of Securities` → fund_raise/allotment, except when the text matches `ESOP|ESOS|ESPS|employee stock` → unclassified/esop.
  - `ESOP/ESOS/ESPS` → unclassified/esop.
  - `Capacity addition`, `Commencement of commercial production/operations`, `Postponement of commercial production/operations` → capex.
  - `Bagging/Receiving of orders/contracts`, `Awarding of order(s)/contract(s)` → press_release/order_win; `Product launch` → press_release/product; `Arrangements for strategic, technical, manufacturing, or marketing tie up`, `Memorandum of Understanding/Agreements`, `Agreements` → press_release/partnership.
  - `Dividend`, `Record Date`, `Date of payment of dividend`, `Revised Record date` → dividend; `Bonus`, `Stock split` → bonus_split.
  - `Investor Presentation` → results/presentation; `Integrated Filing- Financial`, `Clarification - Financial Results`, `Reply to Clarification- Financial results` → results/filing; `Reasons for Delayed/Non-submission of Financial Results` → results/delay.
  - `Disclosure under SEBI Takeover Regulations` → insider_trading/sast; `Trading Plan under PIT` → insider_trading/plan.
  - `Spurt in Volume`, `Price movement`, `News Verification`, `Rumour Verification - Regulation 30(11)` → press_release/clarification.
  - `Change in Auditors` → unclassified/auditor; `Resignation of Statutory Auditor` → litigation/auditor_resignation (a red flag, so it's deliberately not routine).
  - `Monitoring Agency Report`, `Statement of deviation(s) or variation(s) under Reg. 32`, `Utilisation of Funds` → unclassified/compliance.
  - `Disruption of Operations`, `Strikes/Lockouts/Disturbances`, `Closure of operations` → litigation/disruption.
  - `Suspension of Trading`, `Delisting` → litigation/listing.
- **Ambiguous descs, resolved by first-match keyword rules on `subject + " " + (nse_summary or "")`, case-insensitive:**
  - These apply to `Outcome of Board Meeting`, `Analysts/Institutional Investor Meet/Con. Call Updates`, `General Updates`, `Updates`, `Press Release`, `Press Release (Revised)`, `Shareholders meeting`, `Others`, `Disclosure of material issue`, `Committee Meeting Updates`, `Monthly Business Updates`.
  - Rules, in order:
    1. `transcript` → earnings_call/transcript
    2. `audio|recording` → earnings_call/audio
    3. `(con(ference)?[ .-]?call|earnings call)` → earnings_call/notice
    4. `(financial )?results` + `(approv|unaudited|audited|outcome)` → results/results
    5. `scheduled .* (to consider|inter alia).*results` → results/intimation
    6. `dividend` → dividend
    7. `(acqui|merger|amalgamat|demerg|joint venture|stake)` → mna
    8. `(appoint|resign|cessation|re-?designat|chief executive|chief financial|managing director)` → management_change
    9. `(qip|rights issue|preferential|buyback|fund ?rais|non-convertible|ncd|commercial paper)` → fund_raise
    10. `(postal ballot)` → postal_ballot
    11. `(annual general meeting|\bagm\b|extra-?ordinary general meeting|\begm\b)` → agm_egm
    12. `(investor|analyst).*(meet|conference)` → investor_meetings
    13. `(order|contract)` → press_release/order_win
    14. `(capacity|plant|capex|expansion)` → capex
    15. `(monthly|business update|sales)` → press_release/business_update
  - If nothing matches, return `None`.
- **Management subtype role regex:** `(chief executive|ceo|chief financial|cfo|managing director|\bmd\b|whole[- ]?time director|chairman|chairperson)` → `cxo`; `(independent director|non-executive)` → `independent`; `(company secretary|compliance officer)` → `cs`; else `director`.
- `confidence`: 0.95 for DESC_MAP hits, 0.8 for keyword hits.

- [ ] **Step 1: Write failing table-driven test `test_rules_table`.** At least 20 `(nse_desc, subject, expected_category, expected_subtype_or_None, expected_noise)` rows copied from the fixtures. It must include:
  - RELIANCE 30-Oct "Outcome of Board Meeting" → results/results
  - RELIANCE 01-Nov "Transcript of the discussion…" (desc Analysts/…) → earnings_call/transcript
  - RELIANCE 27-Oct "The meeting of the Board … scheduled on October 30, 2026 … to consider" → results/intimation
  - a "Copy of Newspaper Publication" → noise
  - an "Appointment" whose subject names a CFO → management_change/cxo
  - "Resignation of Statutory Auditor" → litigation/auditor_resignation
- [ ] **Step 2:** Add `test_ambiguous_returns_none`: "General Updates" with subject "Trading in equity shares of Jio Platforms Limited (JPL) will commence" → `None`.
- [ ] **Step 3:** Run them and confirm they FAIL; implement `rules.py`; run them and confirm they PASS.
- [ ] **Step 4:** Run `test_rules_coverage` over `portfolio_month.json`: rules classify ≥ 80% of filings (print the uncovered `nse_desc` counts on failure). Commit `feat(classify): rule-based classifier`.

### Task 5: LLM router (Groq + Gemini), cache, cost log

**Files:**
- Create: `backend/finn/llm/__init__.py`, `backend/finn/llm/router.py`, `backend/finn/llm/providers.py`, `backend/finn/llm/costs.py`
- Modify: `backend/finn/config.py` (add `ROUTES` and model IDs)
- Test: `backend/tests/test_llm_router.py`

**Interfaces:**
- Consumes: `connect`/tables `llm_cache`, `llm_calls` (Task 2), `Settings`.
- Produces: `class LLMError(Exception)`; `class LLMRouter(conn, settings, transport: httpx.BaseTransport | None = None)` with:
  - `complete_json(task: str, system: str, user: str, *, doc_hash: str = "") -> dict` (returns parsed JSON; raises `LLMError` after retries)
  - `stats() -> dict` (`{"calls": int, "cached": int, "input_tokens": int, "output_tokens": int, "usd_list_price": float}`)
- `ROUTES: dict[str, tuple[Literal["groq","gemini"], str]]` with tasks:
  - `classify` → groq small Llama
  - `oneliner` → groq small Llama
  - `extract_pdf` → gemini flash
  - `extract_transcript` → gemini flash-lite
  - `reason` → gemini pro-class (or flash + thinking if Pro has no free quota)
  - `bio` → gemini flash
  - Model IDs are verified now via `GET https://api.groq.com/openai/v1/models` and `GET https://generativelanguage.googleapis.com/v1beta/models`, and recorded with a `# checked 2026-11-DD` comment.
- **Groq:** OpenAI-compatible `POST https://api.groq.com/openai/v1/chat/completions` with `response_format={"type":"json_object"}`, temperature 0.
- **Gemini:** `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` with `generationConfig.responseMimeType="application/json"`, temperature 0.
- **Cache key:** `sha256(provider|model|system|user|doc_hash)`. A cache hit makes no HTTP call and logs a row with `cached=1`.
- **Cost:** `costs.py` holds a `LIST_PRICES_PER_MTOK` dict (input/output USD per model at paid list price, looked up at implementation time). Every call logs `usd_list_price` so the UI and README can report "₹0 spent on free tier; would be $X at list price".
- **Retries:** on 429/5xx, honour `retry-after`, otherwise backoff 1/2/4 s, max 3; then raise `LLMError`. Code fences are stripped before `json.loads`.

- [ ] **Step 1: Write failing tests (respx, no network):**
  - `test_groq_json_roundtrip`
  - `test_cache_hit_skips_http`: the second identical call makes 0 extra requests and `stats()["cached"] == 1`.
  - `test_429_then_ok`
  - `test_invalid_json_raises_llmerror`
  - `test_usage_logged`: input/output tokens are taken from the provider's `usage` / `usageMetadata`.
- [ ] **Step 2:** Run them and confirm they FAIL; implement; run them and confirm they PASS.
- [ ] **Step 3 (needs keys):** Live smoke test: `uv run python -c "…LLMRouter(...).complete_json('classify', 'Reply JSON', '{\"ping\":1}')"` against both providers. Output: valid JSON from each. Commit `feat(llm): routed, cached, cost-logged LLM client`.

### Task 6: LLM fallback classifier

**Files:**
- Create: `backend/finn/classify/llm.py`, `backend/finn/classify/pipeline.py`
- Test: `backend/tests/test_classify_llm.py`

**Interfaces:**
- Consumes: `classify_rules` (Task 4), `LLMRouter.complete_json` (Task 5), `unclassified_filings` and `save_classifications` (Task 2).
- Produces:
  - `classify_batch_llm(router: LLMRouter, filings: list[Filing], batch_size: int = 20) -> dict[str, Classification]`
  - `classify_pending(conn, router: LLMRouter | None) -> dict[str, int]`. It runs rules first, then the LLM for the leftovers, or `default` when the router is `None`. Returns counts `{"rules": n, "llm": n, "default": n}`.
- Prompt: the system prompt carries the 17 category definitions verbatim from the reference doc plus "routine = unclassified". The user message is a JSON list of `{id, desc, subject, summary[:400]}`. The expected reply is `{"items":[{"id":…, "category":…, "subtype":…|null}]}`. `confidence` is 0.7.

- [ ] **Step 1: Write failing tests with a `FakeRouter`:**
  - `test_batches_of_20`: 45 filings produce 3 calls.
  - `test_bad_llm_output_defaults`: a reply with an unknown category or a missing id gives `unclassified`, `by="default"`.
  - `test_llmerror_defaults_whole_batch`
  - `test_pending_uses_rules_first`: filings matched by rules never reach the router.
- [ ] **Step 2:** Run them and confirm they FAIL; implement; run them and confirm they PASS. Commit `feat(classify): LLM fallback for ambiguous filings`.

### Task 7: Materiality scoring and story clustering

**Files:**
- Create: `backend/finn/classify/materiality.py`, `backend/finn/classify/cluster.py`
- Modify: `backend/finn/models.py` (add `ScoredFiling`, `Story`)
- Test: `backend/tests/test_materiality.py`, `backend/tests/test_cluster.py`

**Interfaces:**
- Produces:
  - `ScoredFiling(filing: Filing, cls: Classification, score: int, tier: Literal["critical","important","routine","noise"], reasons: list[str])`
  - `Story(id: str, symbol: str, company: str, category: Category, subtype: str | None, score: int, tier: …, headline: ScoredFiling, members: list[ScoredFiling], latest_at: datetime)`
  - `score_filing(f: Filing, cls: Classification, subscribed: set[Category]) -> ScoredFiling`
  - `cluster(scored: list[ScoredFiling], window_hours: int = 48) -> list[Story]` (sorted by score desc, then `latest_at` desc)
- **Modifiers** (score is `round(base × modifier)`, capped at 100). Each modifier appends a human-readable reason, e.g. `"CFO change ×1.1"`.
  - management_change: cxo ×1.1; independent ×0.6; cs ×0.6
  - credit_rating: downgrade ×1.15; reaffirm ×0.35; new ×0.7
  - results: intimation ×0.3; delay ×0.9; presentation ×0.9
  - earnings_call: transcript ×1.5; audio ×0.5; notice ×0.5
  - press_release: order_win ×1.3
  - fund_raise: allotment ×0.6
  - litigation: auditor_resignation ×1.1
- **Subscription boost:** +10 when the category is in `subscribed` (reason `"you follow <cat>"`).
- **Clustering:** same `symbol` and same `category`, with each member within `window_hours` of the cluster's first filing. No filing is ever dropped, because same-subject twins carry different PDFs. `Story.id = f"{symbol}:{category}:{first.seq_id}"`. The headline is the highest-scoring member. Story score = max member score.

- [ ] **Step 1: Write failing tests:**
  - `test_base_scores_match_spec` (parametrized over all 17)
  - `test_cfo_change_is_critical` (88 → critical)
  - `test_rating_reaffirm_is_routine` (round(70×0.35) = 24 → routine)
  - `test_transcript_is_important` (45)
  - `test_noise_is_zero`
  - `test_subscription_boost_capped_at_100`
  - `test_reliance_results_cluster`: RELIANCE fixture seq_ids 106837394, 106837395, 106837406 and 106837413 (30-Oct) produce exactly 1 `results` story with 4 members, whose headline is an Outcome of Board Meeting.
  - `test_same_subject_filings_one_story`: two filings with the same subject and timestamp but different `pdf_url` produce 1 story with 2 members, and both `pdf_url`s are present.
  - `test_far_apart_same_category_not_merged` (72 h apart → 2 stories)
- [ ] **Step 2:** Run them and confirm they FAIL; implement; run them and confirm they PASS. Commit `feat(classify): materiality scoring and story clustering`.

### Task 8: EOD prices and alert engine

**Files:**
- Create: `backend/finn/ingest/prices.py`, `backend/finn/alerts.py`
- Modify: `backend/finn/models.py` (add `Rules`, `SymbolOverride`, `Alert`)
- Test: `backend/tests/test_alerts.py`, `backend/tests/test_prices.py`

**Interfaces:**
- Produces:
  - `SymbolOverride(volume_multiple: float | None = None, price_move_pct: float | None = None, muted: bool = False)`
  - `Rules(volume_multiple: float = 2.0, price_move_pct: float = 5.0, lookback: int = 20, categories: set[Category] = {"results","mna","management_change","credit_rating","litigation","pledging","fund_raise"}, overrides: dict[str, SymbolOverride] = {})`
  - `Alert(kind: Literal["volume","price","filing"], symbol: str, date: date, value: float, threshold: float, message: str, story_id: str | None = None)`
  - `fetch_eod(holdings: list[Holding], period: str = "3mo") -> list[PriceBar]` (one batched `yf.download(..., group_by="ticker", auto_adjust=False)`; rows with NaN close are dropped)
  - `completed_sessions(bars: list[PriceBar], now: datetime) -> list[PriceBar]`: drops a bar dated today (IST) when `now` < 15:45 IST. Drops weekend-dated bars whose volume < 25% of the median of the previous 20 (special/Muhurat sessions).
  - `evaluate_prices(history: dict[str, list[PriceBar]], rules: Rules, sessions: int = 5) -> list[Alert]`
  - `evaluate_filings(stories: list[Story], rules: Rules) -> list[Alert]` (stories whose category is in `rules.categories` and tier ∈ {critical, important})
- **Volume:** a bar's volume ÷ mean volume of the `lookback` bars before it; requires ≥ 10 prior bars. **Price:** close-to-close % vs the previous bar. Each of the last `sessions` bars is checked.
- Message copy, exactly:
  - `"{symbol} traded {x:.1f}× its 20-day average volume"`
  - `"{symbol} {up|down} {abs(p):.1f}% on the day"`

- [ ] **Step 1: Write failing tests (synthetic bars):**
  - `test_volume_2_1x_triggers_at_2_not_2_5`
  - `test_price_minus_5_2_triggers`
  - `test_override_beats_global`
  - `test_muted_symbol_no_alerts`
  - `test_insufficient_history_no_volume_alert`
  - `test_muhurat_bar_excluded`: Sun 2026-11-08 with volume 301,518 vs ~5M median is dropped.
  - `test_inprogress_bar_dropped`: now = 2026-11-09 11:00 IST drops the 11-09 bar, while 16:00 IST keeps it.
  - `test_filing_alerts_respect_categories`
- [ ] **Step 2:** Run them and confirm they FAIL; implement; run them and confirm they PASS.
- [ ] **Step 3:** Live check: `uv run python -c "from finn.ingest.prices import fetch_eod; …"` returns ≥ 40 bars for each of the 18 holdings. If yfinance is rate-limited, retry after 60 s; if it still fails, record that in DESIGN.md and add a fallback (NSE historical endpoint) as a follow-up task. Commit `feat: EOD prices and configurable alert engine`.

### Task 9: HTTP API

**Files:**
- Create: `backend/finn/api/__init__.py`, `backend/finn/api/main.py`, `backend/finn/api/deps.py`, `backend/finn/digest.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `build_digest(conn, symbols: list[str], start: datetime, end: datetime, floor: Literal["critical","important","everything"], subscribed: set[Category]) -> dict`
  - FastAPI `app`, with CORS from `settings.allowed_origins`.
- Routes (JSON):
  - `GET /health` → `{"ok": true, "filings_as_of": str|null, "prices_as_of": str|null}`
  - `GET /portfolio` → `{"as_of", "holdings": [{symbol, name, sector, size, close, change_pct, vol_ratio, spark: list[float] (last 20 closes)}]}`. `vol_ratio` = last completed bar volume ÷ mean of the prior 20.
  - `POST /digest`, body `{"hours": int = 24 | "start": iso, "end": iso, "floor": "important", "subscribed": [cat]}` → `{"window": {start, end}, "as_of", "counts": {"shown": n, "routine": n, "hidden": n, "filings": n}, "stories": [Story], "routine": {category: [Story]}, "hidden": [{symbol, subject, filed_at}]}`. POST is used because the preferences travel in the body.
  - `POST /alerts`, body `Rules` → `{"as_of", "alerts": [Alert]}` (price alerts + filing alerts over the last 7 days, newest first)
  - `GET /filings/{seq_id}` → `ScoredFiling` or 404.
- The DB path comes from `Settings`. Tests override the dependency with a temp DB seeded from fixtures.

- [ ] **Step 1: Write failing tests (FastAPI `TestClient`):**
  - `test_health`
  - `test_digest_default_24h_window_shape`
  - `test_digest_floor_moves_items_between_shown_and_routine` (critical vs everything)
  - `test_digest_empty_window`: a weekend window with 0 filings returns 200, `counts.filings == 0`, `stories == []`.
  - `test_alerts_accept_custom_rules` (`price_move_pct` 0.1 → many alerts; 50 → none)
  - `test_portfolio_has_18_rows_with_spark`
  - `test_unknown_filing_404`
- [ ] **Step 2:** Run them and confirm they FAIL; implement; run them and confirm they PASS.
- [ ] **Step 3:** Run `uv run uvicorn finn.api.main:app --port 8000` and `curl -s -X POST localhost:8000/digest -H 'content-type: application/json' -d '{"hours":168}' | head -c 600`. Expect real stories. Commit `feat(api): digest, portfolio, alerts endpoints`.

### Task 10: Refresh job, seed snapshot, classification eval

**Files:**
- Create: `backend/scripts/refresh.py`, `backend/scripts/eval_classify.py`, `backend/tests/fixtures/gold/classification.jsonl`, `docs/EVALS.md`
- Create (artifact): `backend/seed/finn.sqlite`
- Modify: `backend/finn/api/main.py` (on startup, copy `seed/finn.sqlite` to `settings.db_path` if the latter doesn't exist)

**Interfaces:**
- Consumes: `ingest_filings`, `fetch_eod`, `upsert_prices`, `classify_pending`, `LLMRouter`.
- Produces: `refresh(conn, days: int = 30, use_llm: bool = True) -> dict` (summary counts), with CLI `uv run python scripts/refresh.py --days 30 [--no-llm] [--out seed/finn.sqlite]`.
- Gold set: ≥ 80 rows sampled from `portfolio_month.json`, stratified to cover every NSE `desc` present at least once, plus ≥ 25 rows from the ambiguous descs. Row shape: `{"seq_id","nse_desc","subject","summary","category","subtype","noise"}`. Labels are written by Claude from the subject and summary per the reference taxonomy. **EVALS.md must say so, and the user spot-checks 20 rows.**
- Eval output: overall accuracy, accuracy on material categories (score base ≥ 45), rules coverage %, and a confusion list of misses. Also written into `docs/EVALS.md`.

- [ ] **Step 1:** Write the gold file. Write `eval_classify.py`. Run it with rules only (`--no-llm`), then with the LLM. Expected: it prints both result tables, and material-category accuracy is ≥ 90% with the LLM. If not, fix the rules or prompt; never edit the gold labels to fit.
- [ ] **Step 2:** Run `uv run python scripts/refresh.py --days 30 --out seed/finn.sqlite`. Expect: 18/18 symbols ingested, price bars for 18 holdings, 0 unclassified left. Commit the seed DB (`git add -f backend/seed/finn.sqlite`), the eval script, gold set and EVALS.md: `feat: refresh job, seed snapshot, classification eval`.
- [ ] **Step 3:** Run the full suite with `uv run pytest -q`. Expect all tests to pass. Run `uv run ruff check .` and expect it to be clean.

### Task 11: Hugging Face reachability probe (needs the user's HF write token)

**Files:**
- Create (throwaway, not committed): `$SCRATCHPAD/hf-probe/{app.py, Dockerfile, requirements.txt, README.md}`

**Interfaces:**
- Produces: a decision recorded in `docs/DESIGN.md` §Robustness: **in-Space refresh** (NSE + Yahoo + screener all reachable from HF) vs **external refresh** (GitHub Actions/local `refresh.py` pushes the snapshot).

- [ ] **Step 1:** Write a minimal FastAPI app. `GET /probe` calls the following and returns `{name: {status, ms, sample}}`:
  - NSE announcements (RELIANCE, last 7 days)
  - `yf.download("TCS.NS", period="5d")`
  - screener `/company/TCS/consolidated/`
  - one BSE `AnnPdfOpen` transcript URL
  - `nsearchives` PDF
  - Use a Docker Space with `sdk: docker` and `app_port: 7860`.
- [ ] **Step 2:** Create the Space and upload it with `huggingface_hub.HfApi().create_repo(..., repo_type="space", space_sdk="docker")` + `upload_folder`. Wait for build, then `curl https://<user>-finn-probe.hf.space/probe`. Expect a JSON status for all 5.
- [ ] **Step 3:** Record the results and decision in DESIGN.md, then delete the probe Space. Commit `docs: record HF reachability decision`.
