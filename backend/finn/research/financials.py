"""Deterministic trajectory and balance-sheet health from screener annual tables.

All arithmetic lives here; the LLM only narrates the results. Every computation tolerates
missing rows or columns and yields None instead of raising.
"""

from __future__ import annotations

import re

from finn.models import BalanceSheetHealth, Flag, Trajectory

Table = dict[str, dict[str, float]]
_COL = re.compile(r"^([A-Z][a-z]{2}) (\d{4})$")
_LENDER_NOTE = (
    "Lender: leverage and working capital are judged on capital adequacy and asset quality, "
    "which this view does not cover"
)


def is_lender(pl: Table) -> bool:
    labels = {k for row in pl.values() for k in row}
    return "Sales" not in labels and "Revenue" in labels


def _year_end_month(pl: Table) -> str | None:
    for col in reversed(list(pl)):
        m = _COL.match(col)
        if m:
            return m.group(1)
    return None


def _fy_cols(table: Table, month: str | None) -> list[str]:
    """Fiscal-year-end columns (same month every year), oldest first; TTM/half-years excluded."""
    found = []
    for col in table:
        m = _COL.match(col)
        if m and m.group(1) == month:
            found.append((int(m.group(2)), col))
    return [c for _, c in sorted(found)]


def _get(table: Table, col: str, row: str) -> float | None:
    return table.get(col, {}).get(row)


def _cagr(series: list[float | None]) -> float | None:
    pts = [(i, v) for i, v in enumerate(series) if v is not None]
    if len(pts) < 3:
        return None
    (i0, first), (i1, last) = pts[0], pts[-1]
    if first <= 0 or last < 0:
        return None
    return ((last / first) ** (1 / (i1 - i0)) - 1) * 100


def trajectory(pl: Table) -> Trajectory:
    lender = is_lender(pl)
    rev_k, op_k = ("Revenue", "Financing Profit") if lender else ("Sales", "Operating Profit")
    years = _fy_cols(pl, _year_end_month(pl))[-5:]
    rev = [_get(pl, y, rev_k) for y in years]
    op = [_get(pl, y, op_k) for y in years]
    pat = [_get(pl, y, "Net Profit") for y in years]
    margin = [
        o / r * 100 if o is not None and r not in (None, 0) else None
        for o, r in zip(op, rev, strict=True)
    ]
    ms = [m for m in margin if m is not None]
    change = round((ms[-1] - ms[0]) * 100) if len(ms) >= 2 else None
    rev_cagr = _cagr(rev)
    if sum(v is not None for v in rev) < 3:
        read = "insufficient data"
    elif change is not None and change < -100:
        read = "compressing"
    elif rev_cagr is not None and rev_cagr > 0 and change is not None:
        read = "growing"
    else:
        read = "mixed"
    return Trajectory(
        years=years,
        revenue=rev,
        operating_profit=op,
        margin_pct=margin,
        pat=pat,
        revenue_cagr_pct=rev_cagr,
        pat_cagr_pct=_cagr(pat),
        margin_change_bps=change,
        read=read,
        lender=lender,
    )


def _sum3(cols: list[str], getter) -> float | None:
    vals = [getter(c) for c in cols]
    return None if len(vals) < 3 or any(v is None for v in vals) else sum(vals)


def balance_sheet_health(
    pl: Table, bs: Table, cf: Table, ratios: Table, lender: bool
) -> BalanceSheetHealth:
    month = _year_end_month(pl)
    bs_cols = _fy_cols(bs, month)
    as_of = bs_cols[-1] if bs_cols else ""

    eq = _get(bs, as_of, "Equity Capital")
    res = _get(bs, as_of, "Reserves")
    debt = _get(bs, as_of, "Borrowings")
    net_worth = None if eq is None or res is None else eq + res
    de = debt / net_worth if debt is not None and net_worth else None

    cf3 = _fy_cols(cf, month)[-3:]
    cfo = _sum3(cf3, lambda c: _get(cf, c, "Cash from Operating Activity"))
    pat = _sum3(cf3, lambda c: _get(pl, c, "Net Profit"))
    cfo_pat = cfo / pat if cfo is not None and pat else None
    fcf = _sum3(cf3, lambda c: _get(cf, c, "Free Cash Flow"))

    rcols = _fy_cols(ratios, month)
    wc = wc_change = wc_then = None
    if rcols:
        wc = _get(ratios, rcols[-1], "Working Capital Days")
        year = int(rcols[-1][-4:])
        wc_then = _get(ratios, f"{month} {year - 3}", "Working Capital Days")
        wc_change = wc - wc_then if wc is not None and wc_then is not None else None
    roce = _get(ratios, rcols[-1], "ROCE %") if rcols else None

    flags: list[Flag] = []
    if not lender:
        if de is not None and de > 1.0:
            flags.append(Flag(level="concern", text=f"Debt is {de:.1f}× equity"))
        elif de is not None and de < 0.1:
            flags.append(Flag(level="good", text=f"Virtually debt-free (D/E {de:.2f})"))
    if cfo_pat is not None:
        if cfo_pat < 0.7:
            flags.append(
                Flag(
                    level="concern",
                    text=f"Only {cfo_pat:.0%} of profit turned into operating cash over 3 years",
                )
            )
        elif cfo_pat >= 1.0:
            flags.append(
                Flag(level="good", text=f"Profits are backed by cash (CFO/PAT {cfo_pat:.2f})")
            )
    if not lender:
        if wc_change is not None and wc_change > 15:
            flags.append(
                Flag(
                    level="watch",
                    text=f"Working capital days rose from {wc_then:.0f} to {wc:.0f}",
                )
            )
        if fcf is not None and fcf < 0:
            flags.append(
                Flag(
                    level="watch",
                    text=f"Free cash flow was negative over 3 years (₹{fcf:,.0f} cr)",
                )
            )
    else:
        de = fcf = wc = wc_change = None
        flags.append(Flag(level="watch", text=_LENDER_NOTE))

    return BalanceSheetHealth(
        as_of=as_of,
        debt_to_equity=de,
        cfo_to_pat_3y=cfo_pat,
        fcf_3y_cr=fcf,
        working_capital_days=wc,
        wc_days_change_3y=wc_change,
        roce_pct=roce,
        flags=flags,
    )
