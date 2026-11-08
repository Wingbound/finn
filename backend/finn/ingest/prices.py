"""End-of-day prices via yfinance."""

from __future__ import annotations

import logging
from collections.abc import Collection
from datetime import date, datetime, time

import pandas as pd
import yfinance as yf

from finn.config import FULL_SPECIAL_SESSIONS
from finn.models import IST, PriceBar
from finn.portfolio import Holding

log = logging.getLogger(__name__)

SESSION_CLOSE = time(15, 45)  # NSE closes 15:30; allow 15 min for data to settle


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


def completed_sessions(
    bars: list[PriceBar],
    now: datetime,
    full_special_sessions: Collection[date] = FULL_SPECIAL_SESSIONS,
) -> list[PriceBar]:
    """Drop an in-progress bar for today and weekend special (Muhurat) sessions.

    A weekend bar is kept only when its date is in `full_special_sessions`. Volume can't
    separate the two: the 2026 Muhurat hour traded near-normal volume in several names.
    """
    now_ist = now.astimezone(IST)
    today = now_ist.date()
    in_progress = now_ist.time() < SESSION_CLOSE
    return [
        b
        for b in bars
        if not (in_progress and b.date == today)
        and (b.date.weekday() < 5 or b.date in full_special_sessions)
    ]
