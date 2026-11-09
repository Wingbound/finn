"""Digest assembly: score, cluster and tier the filings in a window."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Literal

from pydantic import ValidationError

from finn import db
from finn.classify import default_classification
from finn.classify.cluster import cluster
from finn.classify.materiality import score_filing
from finn.classify.rules import classify_rules
from finn.enrich.brief import attach_briefs
from finn.enrich.people import attach_people
from finn.enrich.results import card_for
from finn.models import Category, Classification, Filing, ResultsCard, ScoredFiling, Story

log = logging.getLogger(__name__)

Floor = Literal["critical", "important", "everything"]

_FLOOR_TIERS: dict[str, set[str]] = {
    "critical": {"critical"},
    "important": {"critical", "important"},
    "everything": {"critical", "important", "routine"},
}


def classification_or_default(f: Filing, cls: Classification | None) -> Classification:
    """Stored classification, else rules on the fly, else unclassified. Never persists."""
    return cls or classify_rules(f) or default_classification()


def score_window(
    conn: sqlite3.Connection,
    symbols: list[str],
    start: datetime,
    end: datetime,
    subscribed: set[Category],
) -> list[ScoredFiling]:
    return [
        score_filing(f, classification_or_default(f, c), subscribed)
        for f, c in db.filings_in_window(conn, symbols, start, end)
    ]


def stories_in_window(
    conn: sqlite3.Connection,
    symbols: list[str],
    start: datetime,
    end: datetime,
    subscribed: set[Category],
) -> list[Story]:
    return cluster(score_window(conn, symbols, start, end, subscribed))


_CARD_WINDOW = timedelta(days=4)


def _card_or_none(conn: sqlite3.Connection, symbol: str) -> tuple[ResultsCard, datetime] | None:
    """The symbol's latest card, or None when there is none or its stored rows are corrupt."""
    try:
        found = card_for(conn, symbol)
        if found is not None and found[1].utcoffset() is None:
            raise ValueError(f"filed_at {found[1].isoformat()} has no timezone")
    except (ValidationError, ValueError, KeyError, TypeError) as e:
        log.warning("numbers pending for %s: corrupt financials: %s", symbol, type(e).__name__)
        return None
    return found


def attach_results(conn: sqlite3.Connection, stories: list[Story]) -> None:
    """Give each results story its symbol's latest card, when that card is for this filing.

    The card's filed_at must be within 4 days of the headline filing, so a stale quarter's
    numbers never sit on a new story. One card lookup per symbol per call. A symbol whose
    stored financials are corrupt gets no card ("numbers pending") instead of a 500.
    """
    cache: dict[str, tuple[ResultsCard, datetime] | None] = {}
    for st in stories:
        if st.category != "results" or st.subtype == "intimation":
            continue
        if st.symbol not in cache:
            cache[st.symbol] = _card_or_none(conn, st.symbol)
        found = cache[st.symbol]
        if found and abs(found[1] - st.headline.filing.filed_at) <= _CARD_WINDOW:
            st.results = found[0]


def build_digest(
    conn: sqlite3.Connection,
    symbols: list[str],
    start: datetime,
    end: datetime,
    floor: Floor,
    subscribed: set[Category],
) -> dict:
    scored = score_window(conn, symbols, start, end, subscribed)
    stories = cluster(scored)

    hidden = [
        {
            "symbol": s.filing.symbol,
            "subject": s.filing.subject,
            "filed_at": s.filing.filed_at.isoformat(),
        }
        for s in scored
        if s.tier == "noise"
    ]
    shown: list[Story] = []
    routine: dict[str, list[Story]] = {}
    for st in stories:
        if st.tier == "noise":
            continue
        if st.tier in _FLOOR_TIERS[floor]:
            shown.append(st)
        else:
            routine.setdefault(st.category, []).append(st)

    visible = shown + [st for v in routine.values() for st in v]
    attach_results(conn, visible)
    attach_people(conn, visible)
    attach_briefs(conn, visible)

    latest = db.latest_filed_at(conn, symbols)
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "as_of": db.get_meta(conn, "filings_as_of"),
        # newest filing regardless of window, so an empty digest can say how stale the store is
        "latest_filing_at": latest.isoformat() if latest else None,
        "counts": {
            "shown": len(shown),
            "routine": sum(len(v) for v in routine.values()),
            "hidden": len(hidden),
            "filings": len(scored),
        },
        "stories": shown,
        "routine": routine,
        "hidden": hidden,
    }
