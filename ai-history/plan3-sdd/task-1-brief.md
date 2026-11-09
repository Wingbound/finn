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

