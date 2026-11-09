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

