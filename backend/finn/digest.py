"""Digest assembly: score, cluster and tier the filings in a window."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Literal

from finn import db
from finn.classify.cluster import cluster
from finn.classify.materiality import score_filing
from finn.classify.rules import classify_rules
from finn.models import Category, Classification, Filing, ScoredFiling, Story

Floor = Literal["critical", "important", "everything"]

_FLOOR_TIERS: dict[str, set[str]] = {
    "critical": {"critical"},
    "important": {"critical", "important"},
    "everything": {"critical", "important", "routine"},
}


def classification_or_default(f: Filing, cls: Classification | None) -> Classification:
    """Stored classification, else rules on the fly, else unclassified. Never persists."""
    return (
        cls
        or classify_rules(f)
        or Classification(category="unclassified", by="default", confidence=0.0)
    )


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
        {"symbol": s.filing.symbol, "subject": s.filing.subject, "filed_at": s.filing.filed_at.isoformat()}
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

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "as_of": db.get_meta(conn, "filings_as_of"),
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
