"""End-of-day prices via yfinance."""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, time

import pandas as pd
import yfinance as yf

from finn.models import IST, PriceBar
from finn.portfolio import Holding

log = logging.getLogger(__name__)

SESSION_CLOSE = time(15, 45)  # NSE closes 15:30; allow 15 min for data to settle
SPECIAL_SESSION_VOLUME_RATIO = 0.25
SPECIAL_SESSION_LOOKBACK = 20


def fetch_eod(holdings: list[Holding], period: str = "3mo") -> list[PriceBar]:
    tickers = [h.yahoo for h in holdings]
    frame = yf.download(
        tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        progress=False,
        auto_adjust=False,
    )
    bars: list[PriceBar] = []
    for h in holdings:
        try:
            sub = frame[h.yahoo]
        except KeyError:
            log.warning("no price data for %s", h.yahoo)
            continue
        sub = sub.dropna(subset=["Close"])
        if sub.empty:
            log.warning("no price data for %s", h.yahoo)
            continue
        for ts, row in sub.iterrows():
            vol = row["Volume"]
            bars.append(
                PriceBar(
                    symbol=h.symbol,
                    date=pd.Timestamp(ts).date(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=0 if pd.isna(vol) else int(vol),
                )
            )
    return bars


def completed_sessions(bars: list[PriceBar], now: datetime) -> list[PriceBar]:
    """Drop an in-progress bar for today and weekend special (Muhurat) sessions."""
    now_ist = now.astimezone(IST)
    today = now_ist.date()
    in_progress = now_ist.time() < SESSION_CLOSE

    kept: list[PriceBar] = []
    by_symbol: dict[str, list[PriceBar]] = {}
    for b in bars:
        by_symbol.setdefault(b.symbol, []).append(b)
    for series in by_symbol.values():
        series.sort(key=lambda b: b.date)
        for i, b in enumerate(series):
            if in_progress and b.date == today:
                continue
            if b.date.weekday() >= 5:
                prior = [p.volume for p in series[:i]][-SPECIAL_SESSION_LOOKBACK:]
                if prior and b.volume < SPECIAL_SESSION_VOLUME_RATIO * statistics.median(prior):
                    continue
            kept.append(b)
    return kept
