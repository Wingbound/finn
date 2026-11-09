"""FINN HTTP API."""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import statistics
import threading
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta
from time import monotonic
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from finn import db
from finn.alerts import evaluate_filings, evaluate_prices
from finn.api.deps import ensure_seeded, get_conn, get_now
from finn.api.seed import copy_seed_if_empty  # noqa: F401  (re-exported for scripts and tests)
from finn.classify.materiality import score_filing
from finn.config import get_settings
from finn.digest import (
    Floor,
    build_digest,
    card_or_none,
    classification_or_default,
    stories_in_window,
)
from finn.ingest import screener
from finn.ingest.prices import completed_sessions
from finn.llm import LLMRouter
from finn.models import (
    IST,
    Alert,
    Category,
    Dossier,
    PriceBar,
    ResultsCard,
    Rules,
    ScoredFiling,
    public,
)
from finn.portfolio import load_portfolio
from finn.research.cite import dossier_citations
from finn.research.pipeline import build_dossier, is_degraded

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_seeded(get_settings())  # also done lazily per request: serverless may skip lifespan
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
        "seeded": conn.execute("SELECT 1 FROM filings LIMIT 1").fetchone() is not None,
        "cors": get_settings().allowed_origins,
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


# ---- research dossiers ----
CACHE_MINUTES = 10
KEPT_STORED = "Live rebuild was incomplete; showing the last complete dossier"


def _counts(d: Dossier) -> dict:
    return {
        "sources": len(d.sources),
        "ledger_rows": len(d.ledger.rows) if d.ledger else 0,
        "bull": len(d.bull),
        "bear": len(d.bear),
        "notes": len(d.notes),
        "ledger": dict(d.ledger.counts) if d.ledger else {},
    }


@app.get("/research")
def research_list(conn: Conn) -> list[dict]:
    return [
        {
            "symbol": d.symbol,
            "name": d.name,
            "built_at": d.built_at.isoformat(),
            "counts": _counts(d),
        }
        for d in db.list_dossiers(conn)
    ]


@app.get("/research/search")
def research_search(q: Annotated[str, Query(min_length=1)]) -> list[dict]:
    try:
        return screener.search(q)
    except screener.ScreenerError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/research/{symbol}", response_model=None)
def research_get(symbol: str, conn: Conn) -> dict | JSONResponse:
    sym = symbol.upper()
    d = db.get_dossier(conn, sym)
    if d is None:
        return JSONResponse(
            status_code=404, content={"detail": "not built", "build": f"/research/{sym}/build"}
        )
    return public(d)


@app.get("/research/{symbol}/source/{source_id}/{page}")
def research_source_page(symbol: str, source_id: str, page: int, conn: Conn) -> dict:
    d = db.get_dossier(conn, symbol.upper())
    src = next((s for s in d.sources if s.id == source_id), None) if d else None
    if src is None or not 1 <= page <= len(src.pages):
        raise HTTPException(status_code=404, detail="source page not found")
    return {"title": src.title, "page": page, "text": src.pages[page - 1]}


_DONE = object()
PING_S = 15  # keep-alive comment while a build stage is quiet
STREAM_LIMIT_S = 285  # Vercel cuts functions at 300 s


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _excerpts(d: Dossier) -> dict[str, dict[str, str]]:
    """{source_id: {page: text}} for every page the dossier cites (FACTS excluded), so the
    client can show a live-built dossier's citations without another request."""
    by_id = {s.id: s for s in d.sources}
    out: dict[str, dict[str, str]] = {}
    for _, c in dossier_citations(d):
        src = by_id.get(c.source_id)
        if src is not None and 1 <= c.page <= len(src.pages):
            out.setdefault(c.source_id, {})[str(c.page)] = src.pages[c.page - 1]
    return out


def _done(d: Dossier) -> tuple[str, dict]:
    return "done", {**public(d), "excerpts": _excerpts(d)}


def _build_worker(symbol: str, q: queue.Queue) -> None:
    """Runs in its own thread with its own connection and router (sqlite is thread-bound).
    `done` goes on the queue before the save, so a failed save cannot cost the client its
    dossier, and _DONE is always queued last, whatever fails."""
    conn = None
    try:
        try:
            settings = get_settings()
            conn = db.connect(settings.db_path)
            db.init_db(conn)
            router = LLMRouter(conn, settings)
            d = build_dossier(
                conn, symbol, router, progress=lambda m: q.put(("progress", {"msg": m}))
            )
            stored = db.get_dossier(conn, d.symbol)
            keep = is_degraded(d) and stored is not None and not is_degraded(stored)
            if keep:
                assert stored is not None
                q.put(("progress", {"msg": KEPT_STORED}))
                q.put(_done(stored))
            else:
                q.put(_done(d))
                try:
                    db.save_dossier(conn, d)
                except Exception:
                    log.exception("saving the dossier failed for %s", symbol)
        except screener.ScreenerError as e:
            q.put(("error", {"detail": str(e) or f"{symbol} not found on screener"}))
        except Exception as e:
            log.exception("dossier build failed for %s", symbol)
            q.put(("error", {"detail": f"build failed: {type(e).__name__}"}))
        finally:
            if conn is not None:
                conn.close()
    finally:
        q.put(_DONE)


def _stream(q, clock=monotonic):
    """SSE frames from the worker queue: a ": ping" comment every PING_S of silence, and an
    error event once STREAM_LIMIT_S has passed (the worker may still finish and save)."""
    start = clock()
    while (left := STREAM_LIMIT_S - (clock() - start)) > 0:
        try:
            item = q.get(timeout=min(PING_S, left))
        except queue.Empty:
            if STREAM_LIMIT_S - (clock() - start) > 0:
                yield ": ping\n\n"
            continue
        if item is _DONE:
            return
        yield _sse(*item)
    yield _sse("error", {"detail": "build timed out"})


@app.get("/research/{symbol}/build")
def research_build(symbol: str, conn: Conn) -> StreamingResponse:
    sym = symbol.upper()
    cached = db.get_dossier(conn, sym)
    fresh = cached is not None and datetime.now(IST) - cached.built_at < timedelta(
        minutes=CACHE_MINUTES
    )
    q: queue.Queue = queue.Queue()
    if fresh:
        assert cached is not None
        q.put(("progress", {"msg": "Using cached dossier"}))
        q.put(_done(cached))
        q.put(_DONE)
    else:
        threading.Thread(target=_build_worker, args=(sym, q), daemon=True).start()

    return StreamingResponse(
        _stream(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
