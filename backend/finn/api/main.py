"""FINN HTTP API."""

from __future__ import annotations

import logging
import shutil
import sqlite3
import statistics
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from finn import db
from finn.alerts import evaluate_filings, evaluate_prices
from finn.api.deps import get_conn, get_now
from finn.classify.materiality import score_filing
from finn.config import get_settings
from finn.digest import (
    Floor,
    build_digest,
    card_or_none,
    classification_or_default,
    stories_in_window,
)
from finn.ingest.prices import completed_sessions
from finn.models import IST, Alert, Category, PriceBar, ResultsCard, Rules, ScoredFiling
from finn.portfolio import load_portfolio

log = logging.getLogger(__name__)


def _has_filings(db_path: Path) -> bool:
    """Whether an existing SQLite file holds any filings (raises sqlite3.DatabaseError)."""
    conn = sqlite3.connect(db_path)
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='filings'"
        ).fetchone()
        return bool(table) and conn.execute("SELECT 1 FROM filings LIMIT 1").fetchone() is not None
    finally:
        conn.close()


def copy_seed_if_empty(db_path: Path, seed_path: Path) -> bool:
    """Start from the committed snapshot when the store is missing or has no filings.

    Scripts that open the serving DB create an empty one as a side effect, so "file exists"
    is not enough. A store with filings, or a file that isn't a readable database, is never
    overwritten.
    """
    if db_path.exists():
        try:
            if _has_filings(db_path):
                return False
        except sqlite3.DatabaseError as e:
            log.warning("not seeding %s: it is not a readable SQLite database (%s)", db_path, e)
            return False
    if not seed_path.exists():
        log.warning("seed snapshot %s not found; %s starts empty", seed_path, db_path)
        return False
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for sidecar in ("-wal", "-shm"):  # an old WAL would be replayed onto the copied seed
        Path(f"{db_path}{sidecar}").unlink(missing_ok=True)
    shutil.copyfile(seed_path, db_path)
    return True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    copy_seed_if_empty(settings.db_path, settings.seed_path)
    yield


app = FastAPI(title="FINN", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
Now = Annotated[datetime, Depends(get_now)]

SPARK_POINTS = 20
VOL_LOOKBACK = 20
VOL_MIN_PRIOR = 10
ALERT_WINDOW_DAYS = 7
ALERT_SESSIONS = 5


class DigestRequest(BaseModel):
    hours: int = Field(24, gt=0, le=24 * 366)
    start: datetime | None = None
    end: datetime | None = None
    floor: Floor = "important"
    subscribed: set[Category] = Field(default_factory=lambda: set(Rules().categories))

    @model_validator(mode="after")
    def _aware(self) -> DigestRequest:
        for name in ("start", "end"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                setattr(self, name, v.replace(tzinfo=IST))
        if self.start and self.end and self.end < self.start:
            raise ValueError("end must not be before start")
        return self


HISTORY_BARS = 60


def _completed_history(
    conn: sqlite3.Connection, symbol: str, now: datetime, bars: int = HISTORY_BARS
) -> list[PriceBar]:
    return completed_sessions(db.price_history(conn, symbol, bars), now)


@app.get("/health")
def health(conn: Conn) -> dict:
    return {
        "ok": True,
        "filings_as_of": db.get_meta(conn, "filings_as_of"),
        "prices_as_of": db.get_meta(conn, "prices_as_of"),
    }


def _holding_row(h, bars) -> dict:
    row = {
        "symbol": h.symbol,
        "name": h.name,
        "sector": h.sector,
        "size": h.size,
        "date": None,
        "close": None,
        "change_pct": None,
        "vol_ratio": None,
        "spark": [],
    }
    if not bars:
        return row
    row["date"] = bars[-1].date.isoformat()  # last completed session; symbols can lag
    row["close"] = bars[-1].close
    row["spark"] = [b.close for b in bars[-SPARK_POINTS:]]
    if len(bars) >= 2 and bars[-2].close > 0:
        row["change_pct"] = round((bars[-1].close / bars[-2].close - 1) * 100, 2)
    prior = [b.volume for b in bars[:-1][-VOL_LOOKBACK:]]
    if len(prior) >= VOL_MIN_PRIOR:
        mean = statistics.fmean(prior)
        if mean > 0:
            row["vol_ratio"] = round(bars[-1].volume / mean, 2)
    return row


@app.get("/portfolio")
def portfolio(conn: Conn, now: Now) -> dict:
    return {
        "as_of": db.get_meta(conn, "prices_as_of"),
        "holdings": [
            _holding_row(h, _completed_history(conn, h.symbol, now)) for h in load_portfolio()
        ],
    }


@app.post("/digest")
def digest(req: DigestRequest, conn: Conn, now: Now) -> dict:
    end = req.end or now
    start = req.start or end - timedelta(hours=req.hours)
    if end < start:  # only reachable when start is given without end and lies after now
        raise HTTPException(status_code=422, detail="start must not be after the end of the window")
    symbols = [h.symbol for h in load_portfolio()]
    return build_digest(conn, symbols, start, end, req.floor, req.subscribed)


def _alert_anchor(
    now: datetime, latest_filing: datetime | None, history: dict[str, list[PriceBar]]
) -> datetime:
    """min(now, newest data point): a stale store still alerts on its last week of data.

    The newest data point is the later of the newest filing and the end of day (IST) of the
    newest completed price bar.
    """
    points = [latest_filing] if latest_filing else []
    last_bar = max((bars[-1].date for bars in history.values() if bars), default=None)
    if last_bar:
        points.append(datetime.combine(last_bar, time.max, IST))
    return min(now, max(points, default=now)).astimezone(IST)


@app.post("/alerts")
def alerts(rules: Rules, conn: Conn, now: Now) -> dict:
    symbols = [h.symbol for h in load_portfolio()]
    # each evaluated session needs `lookback` prior bars; +1 for a possible in-progress bar
    bars = max(HISTORY_BARS, rules.lookback + ALERT_SESSIONS + 1)
    history = {s: _completed_history(conn, s, now, bars) for s in symbols}
    end = _alert_anchor(now, db.latest_filed_at(conn, symbols), history)
    start = end - timedelta(days=ALERT_WINDOW_DAYS)
    # Both kinds share the window: filing stories in [start, end], sessions dated within it.
    stories = stories_in_window(conn, symbols, start, end, set(rules.categories))
    merged: list[Alert] = evaluate_prices(
        history, rules, ALERT_SESSIONS, start=start.date(), end=end.date()
    ) + evaluate_filings(stories, rules)
    merged.sort(key=lambda a: a.symbol)
    merged.sort(key=lambda a: a.date, reverse=True)
    return {
        "as_of": db.get_meta(conn, "prices_as_of"),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "alerts": merged,
    }


@app.get("/results/{symbol}")
def results_card(symbol: str, conn: Conn) -> ResultsCard:
    found = card_or_none(conn, symbol.upper())
    if found is None:
        raise HTTPException(status_code=404, detail="no results on file")
    return found[0]


@app.get("/filings/{seq_id}")
def filing(
    seq_id: str,
    conn: Conn,
    subscribed: Annotated[list[Category] | None, Query()] = None,
) -> ScoredFiling:
    """One filing, scored like its digest card: pass the digest's `subscribed` (repeatable);
    omitted, it defaults to the digest's default."""
    found = db.get_filing(conn, seq_id)
    if found is None:
        raise HTTPException(status_code=404, detail="filing not found")
    f, cls = found
    subs = set(subscribed) if subscribed is not None else set(Rules().categories)
    return score_filing(f, classification_or_default(f, cls), subs)
