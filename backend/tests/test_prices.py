from datetime import date, datetime

import pandas as pd

from finn.config import FULL_SPECIAL_SESSIONS
from finn.ingest import prices
from finn.ingest.prices import completed_sessions, fetch_eod
from finn.models import IST, PriceBar
from finn.portfolio import Holding


def _bar(d: date, vol: int = 5_000_000, close: float = 100.0, symbol: str = "TCS") -> PriceBar:
    return PriceBar(symbol=symbol, date=d, open=close, high=close, low=close, close=close, volume=vol)


def _weekday_bars(n: int, end: date, vol: int = 5_000_000, symbol: str = "TCS") -> list[PriceBar]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(_bar(d, vol=vol, symbol=symbol))
        d = date.fromordinal(d.toordinal() - 1)
    return sorted(out, key=lambda b: b.date)


def test_muhurat_bar_excluded():
    bars = _weekday_bars(25, date(2026, 11, 6))
    bars.append(_bar(date(2026, 11, 8), vol=301_518))
    out = completed_sessions(bars, datetime(2026, 11, 9, 18, 0, tzinfo=IST))
    assert date(2026, 11, 8) not in {b.date for b in out}
    assert len(out) == 25


def test_muhurat_bar_with_normal_volume_excluded():
    # VOLTAS, Diwali Muhurat 2026-11-08 (Sunday): 648,834 shares against a ~620,300 median,
    # so no volume ratio can tell it apart from a full session.
    bars = _weekday_bars(25, date(2026, 11, 6), vol=620_300, symbol="VOLTAS")
    bars.append(_bar(date(2026, 11, 8), vol=648_834, symbol="VOLTAS"))
    out = completed_sessions(bars, datetime(2026, 11, 9, 18, 0, tzinfo=IST))
    assert date(2026, 11, 8) not in {b.date for b in out}
    assert len(out) == 25


def test_allowlisted_weekend_full_session_kept():
    budget_saturday = date(2026, 11, 7)
    bars = _weekday_bars(25, date(2026, 11, 6)) + [_bar(budget_saturday), _bar(date(2026, 11, 8))]
    out = completed_sessions(
        bars, datetime(2026, 11, 9, 18, 0, tzinfo=IST), full_special_sessions={budget_saturday}
    )
    kept = {b.date for b in out}
    assert budget_saturday in kept and date(2026, 11, 8) not in kept


def test_full_special_sessions_empty_by_default():
    assert FULL_SPECIAL_SESSIONS == frozenset()


def test_inprogress_bar_dropped():
    bars = _weekday_bars(25, date(2026, 11, 6)) + [_bar(date(2026, 11, 9))]
    early = completed_sessions(bars, datetime(2026, 11, 9, 11, 0, tzinfo=IST))
    late = completed_sessions(bars, datetime(2026, 11, 9, 16, 0, tzinfo=IST))
    assert date(2026, 11, 9) not in {b.date for b in early}
    assert date(2026, 11, 9) in {b.date for b in late}


def test_fetch_eod_maps_frame_to_bars(monkeypatch):
    idx = pd.to_datetime(["2026-11-05", "2026-11-06", "2026-11-07"])
    cols = pd.MultiIndex.from_product([["TCS.NS", "M&M.NS"], ["Open", "High", "Low", "Close", "Volume"]])
    nan = float("nan")
    rows = [
        [1, 2, 0.5, 1.5, 100, 10, 12, 9, 11, 50],
        [1, 2, 0.5, 1.6, nan, 10, 12, 9, nan, 60],
        [1, 2, 0.5, 1.7, 300, 10, 12, 9, 13, nan],
    ]
    frame = pd.DataFrame(rows, index=idx, columns=cols)
    monkeypatch.setattr(prices.yf, "download", lambda *a, **k: frame)
    holdings = [
        Holding(symbol="TCS", name="TCS", sector="IT", size="mega"),
        Holding(symbol="M&M", name="M&M", sector="Auto", size="large", yahoo="M&M.NS"),
        Holding(symbol="GHOST", name="Ghost", sector="X", size="small"),
    ]
    bars = fetch_eod(holdings)
    tcs = [b for b in bars if b.symbol == "TCS"]
    mm = [b for b in bars if b.symbol == "M&M"]
    assert [b.date for b in tcs] == [date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 7)]
    assert tcs[0].close == 1.5 and tcs[0].volume == 100
    assert [b.date for b in mm] == [date(2026, 11, 5), date(2026, 11, 7)]  # NaN close dropped
    assert mm[1].volume == 0  # NaN volume -> 0
    assert not [b for b in bars if b.symbol == "GHOST"]
