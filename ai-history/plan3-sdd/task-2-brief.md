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

