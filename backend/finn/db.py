"""SQLite persistence (plain sqlite3)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from finn.models import IST, Classification, Filing, PriceBar

_SCHEMA = """
CREATE TABLE IF NOT EXISTS filings (
    seq_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    company TEXT NOT NULL,
    nse_desc TEXT NOT NULL,
    subject TEXT NOT NULL,
    nse_summary TEXT,
    pdf_url TEXT,
    filed_at TEXT NOT NULL,
    has_xbrl INTEGER NOT NULL,
    category TEXT,
    subtype TEXT,
    noise INTEGER,
    classified_by TEXT,
    confidence REAL
);
CREATE INDEX IF NOT EXISTS idx_filings_symbol_time ON filings(symbol, filed_at);
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    task TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    cached INTEGER NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    usd_list_price REAL
);
"""


def _ts(dt: datetime) -> str:
    """Serialise as IST ISO-8601 so string order equals time order."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(IST).isoformat()


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def upsert_filings(conn: sqlite3.Connection, filings: list[Filing]) -> int:
    """Insert unseen filings; existing rows (and their classification) are untouched."""
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO filings (seq_id, symbol, company, nse_desc, subject, nse_summary,"
        " pdf_url, filed_at, has_xbrl) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (f.seq_id, f.symbol, f.company, f.nse_desc, f.subject, f.nse_summary, f.pdf_url,
             _ts(f.filed_at), int(f.has_xbrl))
            for f in filings
        ],
    )
    conn.commit()
    return conn.total_changes - before


def save_classifications(conn: sqlite3.Connection, items: dict[str, Classification]) -> None:
    conn.executemany(
        "UPDATE filings SET category=?, subtype=?, noise=?, classified_by=?, confidence=?"
        " WHERE seq_id=?",
        [(c.category, c.subtype, int(c.noise), c.by, c.confidence, sid) for sid, c in items.items()],
    )
    conn.commit()


def _filing(row: sqlite3.Row) -> Filing:
    return Filing(
        seq_id=row["seq_id"],
        symbol=row["symbol"],
        company=row["company"],
        nse_desc=row["nse_desc"],
        subject=row["subject"],
        nse_summary=row["nse_summary"],
        pdf_url=row["pdf_url"],
        filed_at=datetime.fromisoformat(row["filed_at"]),
        has_xbrl=bool(row["has_xbrl"]),
    )


def _classification(row: sqlite3.Row) -> Classification | None:
    if row["category"] is None:
        return None
    return Classification(
        category=row["category"],
        subtype=row["subtype"],
        noise=bool(row["noise"]),
        by=row["classified_by"],
        confidence=row["confidence"],
    )


def unclassified_filings(conn: sqlite3.Connection) -> list[Filing]:
    rows = conn.execute(
        "SELECT * FROM filings WHERE category IS NULL ORDER BY filed_at, seq_id"
    ).fetchall()
    return [_filing(r) for r in rows]


def filings_in_window(
    conn: sqlite3.Connection, symbols: list[str], start: datetime, end: datetime
) -> list[tuple[Filing, Classification | None]]:
    """Filings for symbols with start <= filed_at <= end, newest first."""
    if not symbols:
        return []
    marks = ",".join("?" * len(symbols))
    rows = conn.execute(
        f"SELECT * FROM filings WHERE symbol IN ({marks}) AND filed_at >= ? AND filed_at <= ?"
        " ORDER BY filed_at DESC, seq_id DESC",
        [*symbols, _ts(start), _ts(end)],
    ).fetchall()
    return [(_filing(r), _classification(r)) for r in rows]


def upsert_prices(conn: sqlite3.Connection, bars: list[PriceBar]) -> int:
    """Insert or refresh bars; returns the number of newly inserted rows."""
    (before,) = conn.execute("SELECT COUNT(*) FROM prices").fetchone()
    conn.executemany(
        "INSERT INTO prices (symbol, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(symbol, date) DO UPDATE SET open=excluded.open, high=excluded.high,"
        " low=excluded.low, close=excluded.close, volume=excluded.volume",
        [(b.symbol, b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume) for b in bars],
    )
    conn.commit()
    (after,) = conn.execute("SELECT COUNT(*) FROM prices").fetchone()
    return after - before


def price_history(conn: sqlite3.Connection, symbol: str, limit: int = 60) -> list[PriceBar]:
    rows = conn.execute(
        "SELECT * FROM prices WHERE symbol=? ORDER BY date DESC LIMIT ?", (symbol, limit)
    ).fetchall()
    return [
        PriceBar(
            symbol=r["symbol"], date=date.fromisoformat(r["date"]), open=r["open"],
            high=r["high"], low=r["low"], close=r["close"], volume=r["volume"],
        )
        for r in reversed(rows)
    ]


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None
