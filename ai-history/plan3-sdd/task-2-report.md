# Task 2 report

## Implemented
- backend/finn/research/__init__.py, financials.py: is_lender, trajectory, balance_sheet_health (rules and flag text per brief).
- backend/finn/models.py: Flag, Trajectory, BalanceSheetHealth.
- Fiscal-year columns: "Mar YYYY"-style matching `^[A-Z][a-z]{2} \d{4}$`, month taken from the last non-TTM pl column; TTM and half-years excluded.
- Missing rows/columns give None. Lender: D/E, FCF, WC fields None, only the note flag for those; CFO/PAT flag still applies.
- Interpretation: "3y" sums use the last 3 FY columns of cash-flow and all three must be present; WC change = last FY minus the FY three years earlier; CAGR uses first/last available points (n = index gap, needs >=3 points, first>0).

## Tests
backend/tests/test_research_financials.py (13 tests): PERSISTENT exact values (rev CAGR 26.76, PAT CAGR 28.22, margin change +218 bps, D/E 0.061, CFO/PAT 0.9697, FCF 3483, WC 20 -> 50, ROCE 34), lender, insufficient, negative first, compress/mixed, TTM/half-year/non-March, empty input, every flag threshold, lender skipping.

## TDD
RED: `uv run pytest tests/test_research_financials.py -q` -> ModuleNotFoundError: No module named 'finn.research.financials' (collection error).
GREEN: `uv run pytest -q` -> 397 passed; ruff check and format --check clean. (One hand-computed expectation, PAT CAGR 28.21, corrected to 28.22 after the first run.)

## Commit
0477dd2 on feat/pull-research.

## Self-review / concerns
- Flags ordering: D/E, CFO/PAT, WC, FCF, then lender note.
- Margin change uses unrounded margins, then rounds to int bps.
- "growing" requires a computable margin change as well as CAGR > 0; otherwise "mixed".
- Fixture has WC flag firing (20 -> 50) alongside the debt-free flag; CFO/PAT 0.97 gives no flag.

## Fix round 1
Changes (financials.py): lender -> cfo_to_pat_3y None and no CFO/PAT flag; _cagr takes n from year numbers in column labels (missing middle column no longer overstates); cfo_to_pat_3y None when 3y net profit <= 0.
Tests: test_lender_skips_leverage_flags now asserts cfo_to_pat_3y None and flags == [lender note]; new test_loss_making_no_cfo_flag; new test_cagr_uses_year_labels_with_missing_column (100,110,-,133.1,146.41 -> 10.0%).
Command: `uv run pytest -q tests/test_research_financials.py` -> `13 passed in 0.03s`; full `uv run pytest -q` -> `399 passed in 2.35s`; `ruff check .` -> `All checks passed!`; `ruff format --check .` -> `65 files already formatted`.
