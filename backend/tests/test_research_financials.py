from pathlib import Path

import pytest

from finn.ingest.screener import parse_table
from finn.research.financials import balance_sheet_health, is_lender, trajectory

HTML = (Path(__file__).parent / "fixtures/research/PERSISTENT_screener.html").read_text()
PL = parse_table(HTML, "profit-loss")
BS = parse_table(HTML, "balance-sheet")
CF = parse_table(HTML, "cash-flow")
RT = parse_table(HTML, "ratios")
A = pytest.approx
_LENDER_NOTE = (
    "Lender: leverage and working capital are judged on capital adequacy "
    "and asset quality, which this view does not cover"
)


def _pl(rev, op, pat, key="Sales", opk="Operating Profit", start=2020):
    return {
        f"Mar {start + i}": {key: r, opk: o, "Net Profit": p}
        for i, (r, o, p) in enumerate(zip(rev, op, pat, strict=True))
    }


def test_trajectory_persistent():
    t = trajectory(PL)
    assert t.years == ["Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    assert t.revenue == [5711, 8351, 9822, 11939, 14748]
    assert t.operating_profit == [958, 1519, 1676, 2058, 2796]
    assert t.pat == [690, 921, 1093, 1400, 1865]
    assert t.margin_pct == A([16.77, 18.19, 17.06, 17.24, 18.96], abs=0.01)
    assert t.revenue_cagr_pct == A(26.76, abs=0.01)
    assert t.pat_cagr_pct == A(28.22, abs=0.01)
    assert t.margin_change_bps == 218
    assert t.read == "growing"
    assert t.lender is False


def test_is_lender():
    assert is_lender({"Mar 2025": {"Revenue": 1.0}})
    assert not is_lender(PL)
    assert not is_lender({})


def test_trajectory_lender():
    pl = _pl([100, 110, 121], [40, 44, 48], [10, 11, 12], "Revenue", "Financing Profit")
    t = trajectory(pl)
    assert t.lender is True
    assert t.margin_pct == A([40.0, 40.0, 39.67], abs=0.01)
    assert t.margin_change_bps == -33
    assert t.read == "growing"


def test_insufficient_data():
    t = trajectory(_pl([100, 120], [10, 12], [5, 6]))
    assert t.read == "insufficient data"
    assert t.revenue_cagr_pct is None


def test_negative_first_value_no_cagr():
    t = trajectory(_pl([100, 110, 120], [10, 11, 12], [-5, 6, 8]))
    assert t.pat_cagr_pct is None
    assert t.revenue_cagr_pct is not None


def test_compressing_and_mixed():
    assert trajectory(_pl([100, 110, 120], [30, 30, 24], [1, 2, 3])).read == "compressing"
    assert trajectory(_pl([120, 110, 100], [20, 20, 20], [1, 2, 3])).read == "mixed"


def test_excludes_ttm_and_half_year_and_non_march():
    pl = _pl([1, 2, 3], [1, 1, 1], [1, 1, 1])
    pl["TTM"] = {"Sales": 99.0}
    t = trajectory(pl)
    assert t.years == ["Mar 2020", "Mar 2021", "Mar 2022"]
    sep = {f"Sep {y}": {"Sales": float(y)} for y in (2022, 2023, 2024)}
    sep["TTM"] = {"Sales": 1.0}
    assert trajectory(sep).years == ["Sep 2022", "Sep 2023", "Sep 2024"]


def test_missing_everything_is_none():
    t = trajectory({})
    assert t.read == "insufficient data" and t.years == []
    h = balance_sheet_health({}, {}, {}, {}, False)
    assert h.debt_to_equity is None and h.flags == [] and h.as_of == ""


def test_health_persistent():
    h = balance_sheet_health(PL, BS, CF, RT, False)
    assert h.as_of == "Mar 2026"
    assert h.debt_to_equity == A(0.061, abs=0.001)
    assert h.cfo_to_pat_3y == A(0.9697, abs=0.001)
    assert h.fcf_3y_cr == A(3483, abs=0.01)
    assert h.working_capital_days == 50
    assert h.wc_days_change_3y == 30
    assert h.roce_pct == 34
    assert [(f.level, f.text) for f in h.flags] == [
        ("good", "Virtually debt-free (D/E 0.06)"),
        ("watch", "Working capital days rose from 20 to 50"),
    ]


def _h(borrow=100, eq=100, cfo=100, pat=100, fcf=10, wc=(10, 10), lender=False):
    pl = {f"Mar {y}": {"Net Profit": float(pat)} for y in (2023, 2024, 2025, 2026)}
    bs = {"Mar 2026": {"Borrowings": float(borrow), "Equity Capital": float(eq), "Reserves": 0.0}}
    cf = {
        f"Mar {y}": {"Cash from Operating Activity": float(cfo), "Free Cash Flow": float(fcf)}
        for y in (2023, 2024, 2025, 2026)
    }
    rt = {"Mar 2023": {"Working Capital Days": wc[0]}, "Mar 2026": {"Working Capital Days": wc[1]}}
    return balance_sheet_health(pl, bs, cf, rt, lender)


def texts(h):
    return [(f.level, f.text) for f in h.flags]


def test_flag_thresholds():
    assert ("concern", "Debt is 1.5× equity") in texts(_h(borrow=150))
    assert not any("Debt" in t or "debt" in t for _, t in texts(_h(borrow=100)))
    assert ("good", "Virtually debt-free (D/E 0.05)") in texts(_h(borrow=5))
    assert (
        "concern",
        "Only 60% of profit turned into operating cash over 3 years",
    ) in texts(_h(cfo=60))
    assert ("good", "Profits are backed by cash (CFO/PAT 1.00)") in texts(_h(cfo=100))
    assert not any("CFO" in t or "Only" in t for _, t in texts(_h(cfo=90)))
    assert ("watch", "Working capital days rose from 10 to 26") in texts(_h(wc=(10, 26)))
    assert not any("Working" in t for _, t in texts(_h(wc=(10, 25))))
    assert ("watch", "Free cash flow was negative over 3 years (₹-30 cr)") in texts(_h(fcf=-10))


def test_lender_skips_leverage_flags():
    h = _h(borrow=500, fcf=-10, wc=(10, 90), lender=True)
    assert h.debt_to_equity is None and h.fcf_3y_cr is None
    assert h.working_capital_days is None and h.wc_days_change_3y is None
    assert texts(h) == [
        ("good", "Profits are backed by cash (CFO/PAT 1.00)"),
        ("watch", _LENDER_NOTE),
    ]
