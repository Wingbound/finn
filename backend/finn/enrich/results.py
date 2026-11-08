"""Results card math: QoQ/YoY, margins and lender metrics from XBRL facts. No I/O."""

from __future__ import annotations

import calendar
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from finn.ingest.xbrl import QuarterFinancials, XbrlFormat
from finn.models import MarginRow, MetricRow, ResultsCard

CRORE = 1e7

Facts = dict[str, float | None]


def quarter_label(period_end: date) -> str:
    fy = period_end.year + 1 if period_end.month >= 4 else period_end.year
    q = (period_end.month - 4) // 3 + 1 if period_end.month >= 4 else 4
    return f"Q{q} FY{fy % 100:02d}"


def quarter_end_shift(period_end: date, quarters: int) -> date:
    idx = period_end.year * 12 + (period_end.month - 1) + 3 * quarters
    year, month = divmod(idx, 12)
    month += 1
    return date(year, month, calendar.monthrange(year, month)[1])


def _finite(x: float | None) -> bool:
    return x is not None and math.isfinite(x)


def pct_change(cur: float | None, prev: float | None) -> float | None:
    """% change; None when undefined or meaningless (prev <= 0, or a sign flip)."""
    if not _finite(cur) or not _finite(prev):
        return None
    assert cur is not None and prev is not None
    if prev <= 0 or cur < 0:
        return None
    return (cur - prev) / prev * 100


def _sub(a: float | None, *rest: float | None) -> float | None:
    if a is None or any(r is None for r in rest):
        return None
    return a - sum(r for r in rest if r is not None)


@dataclass(frozen=True)
class _Metric:
    key: str
    label: str
    fn: Callable[[Facts], float | None]
    computed: bool = False


def _get(name: str) -> Callable[[Facts], float | None]:
    return lambda f: f.get(name)


_EBITDA: Callable[[Facts], float | None] = lambda f: _sub(
    f.get("RevenueFromOperations"),
    _sub(
        f.get("Expenses"),
        f.get("FinanceCosts"),
        f.get("DepreciationDepletionAndAmortisationExpense"),
    ),
)

_REVENUE = _Metric("revenue", "Revenue", _get("RevenueFromOperations"))
_PBT = _Metric("pbt", "PBT", _get("ProfitBeforeTax"))
_PAT = _Metric("pat", "PAT", _get("ProfitLossForPeriod"))

_METRICS: dict[XbrlFormat, list[_Metric]] = {
    "indas": [_REVENUE, _Metric("ebitda", "EBITDA", _EBITDA, True), _PBT, _PAT],
    "nbfc": [
        _REVENUE,
        _Metric(
            "nii",
            "Net interest income",
            lambda f: _sub(f.get("InterestEarned"), f.get("FinanceCosts")),
            True,
        ),
        _Metric("impairment", "Credit cost", _get("ImpairmentOnFinancialInstruments")),
        _PBT,
        _PAT,
    ],
    "bank": [
        _Metric("interest_earned", "Interest earned", _get("InterestEarned")),
        _Metric(
            "nii",
            "Net interest income",
            lambda f: _sub(f.get("InterestEarned"), f.get("InterestExpended")),
            True,
        ),
        _Metric(
            "ppop",
            "Operating profit (pre-provision)",
            _get("OperatingProfitBeforeProvisionAndContingencies"),
        ),
        _Metric(
            "provisions",
            "Provisions",
            _get("ProvisionsOtherThanTaxAndContingencies"),
        ),
        _Metric("pbt", "PBT", _get("ProfitLossFromOrdinaryActivitiesBeforeTax")),
        _Metric("pat", "PAT", _get("ProfitLossForThePeriod")),
        _Metric("gnpa", "Gross NPA", _get("GrossNonPerformingAssets")),
        _Metric("nnpa", "Net NPA", _get("NonPerformingAssets")),
    ],
}

# margin key, label, numerator metric key (over revenue)
_MARGINS: dict[XbrlFormat, list[tuple[str, str, str]]] = {
    "indas": [
        ("ebitda_margin", "EBITDA margin", "ebitda"),
        ("pat_margin", "PAT margin", "pat"),
    ],
    "nbfc": [("pat_margin", "PAT margin", "pat")],
    "bank": [],
}

_PAT_KEY = "pat"


def _facts_crore(q: QuarterFinancials) -> Facts:
    """Facts in INR crore; non-finite values are treated as missing."""
    return {k: (v / CRORE if math.isfinite(v) else None) for k, v in q.facts.items()}


def metrics_for(q: QuarterFinancials) -> dict[str, float | None]:
    f = _facts_crore(q)
    out: dict[str, float | None] = {}
    for m in _METRICS[q.format]:
        v = m.fn(f)
        out[m.key] = v if _finite(v) else None
    return out


def _margin(vals: dict[str, float | None], num: str) -> float | None:
    n, rev = vals.get(num), vals.get("revenue")
    if n is None or rev is None or rev == 0:
        return None
    return n / rev * 100


def _bps(cur: float | None, prev: float | None) -> int | None:
    if cur is None or prev is None:
        return None
    return round((cur - prev) * 100)


def _r(x: float | None, nd: int) -> float | None:
    return None if x is None else round(x, nd)


def _usable(cur: QuarterFinancials, other: QuarterFinancials | None):
    return other if other is not None and other.basis == cur.basis else None


def build_card(
    cur: QuarterFinancials,
    prev: QuarterFinancials | None,
    year_ago: QuarterFinancials | None,
    sources: list[str],
) -> ResultsCard:
    prev = _usable(cur, prev)
    year_ago = _usable(cur, year_ago)
    cv = metrics_for(cur)
    pv = metrics_for(prev) if prev else {}
    yv = metrics_for(year_ago) if year_ago else {}

    metrics = [
        MetricRow(
            key=m.key,
            label=m.label,
            value=_r(cv[m.key], 2),
            qoq_pct=_r(pct_change(cv[m.key], pv.get(m.key)), 1),
            yoy_pct=_r(pct_change(cv[m.key], yv.get(m.key)), 1),
            computed=m.computed,
        )
        for m in _METRICS[cur.format]
    ]

    margins = []
    for key, label, num in _MARGINS[cur.format]:
        c = _margin(cv, num)
        margins.append(
            MarginRow(
                key=key,
                label=label,
                value_pct=_r(c, 1),
                qoq_bps=_bps(c, _margin(pv, num)) if prev else None,
                yoy_bps=_bps(c, _margin(yv, num)) if year_ago else None,
            )
        )

    notes = _notes(cur, cv, prev, pv, year_ago, yv)
    return ResultsCard(
        symbol=cur.symbol,
        period_end=cur.period_end,
        period_label=quarter_label(cur.period_end),
        basis=cur.basis,
        format=cur.format,
        audited=cur.audited,
        compared_qoq=prev.period_end if prev else None,
        compared_yoy=year_ago.period_end if year_ago else None,
        metrics=metrics,
        margins=margins,
        notes=notes,
        sources=sources,
    )


def _nonzero_crore(q: QuarterFinancials, name: str) -> float | None:
    v = q.facts.get(name)
    if v is None or not math.isfinite(v) or v == 0:
        return None
    return v / CRORE


def _notes(
    cur: QuarterFinancials,
    cv: dict[str, float | None],
    prev: QuarterFinancials | None,
    pv: dict[str, float | None],
    year_ago: QuarterFinancials | None,
    yv: dict[str, float | None],
) -> list[str]:
    notes: list[str] = []
    if cur.format == "indas":
        notes.append(
            "EBITDA is computed: revenue from operations minus operating "
            "expenses (excludes other income)."
        )
    else:
        notes.append(
            "Lenders are shown on net interest income and pre-provision "
            "profit; EBITDA does not apply."
        )

    exc_name = "ExceptionalItems" if cur.format == "bank" else "ExceptionalItemsBeforeTax"
    exc = _nonzero_crore(cur, exc_name)
    if exc is not None:
        notes.append(f"PBT includes an exceptional item of ₹{exc:,.2f} cr.")
    assoc = _nonzero_crore(
        cur,
        "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",
    )
    if assoc is not None:
        notes.append(f"PAT includes ₹{assoc:,.2f} cr share of associates and joint ventures.")

    cpat = cv.get(_PAT_KEY)
    for other, vals in ((prev, pv), (year_ago, yv)):
        if other is None:
            continue
        ppat = vals.get(_PAT_KEY)
        if cpat is None or ppat is None:
            continue
        label = quarter_label(other.period_end)
        if cpat < 0 < ppat:
            notes.append(f"PAT swung to a loss vs {label}.")
        elif ppat < 0 < cpat:
            notes.append(f"PAT turned positive vs {label}.")

    for name, other, shift in (("QoQ", prev, -1), ("YoY", year_ago, -4)):
        if other is None:
            label = quarter_label(quarter_end_shift(cur.period_end, shift))
            notes.append(f"No {name} comparison: {label} figures not on file.")
    return notes
