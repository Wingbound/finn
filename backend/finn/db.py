"""SQLite persistence (plain sqlite3)."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

from finn.ingest.xbrl import QuarterFinancials
from finn.models import IST, Classification, Dossier, Filing, PriceBar

log = logging.getLogger(__name__)

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
CREATE TABLE IF NOT EXISTS financials (
    symbol TEXT NOT NULL,
    period_end TEXT NOT NULL,
    basis TEXT NOT NULL,
    format TEXT NOT NULL,
    period_start TEXT NOT NULL,
    audited INTEGER,
    filed_at TEXT NOT NULL,
    xbrl_url TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    PRIMARY KEY (symbol, period_end, basis)
);
CREATE TABLE IF NOT EXISTS doc_text (
    url TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    chars INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS doc_pages (
    url TEXT NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (url, page)
);
CREATE TABLE IF NOT EXISTS dossiers (
    symbol TEXT PRIMARY KEY,
    built_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrichments (
    seq_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (seq_id, kind)
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
            (
                f.seq_id,
                f.symbol,
                f.company,
                f.nse_desc,
                f.subject,
                f.nse_summary,
                f.pdf_url,
                _ts(f.filed_at),
                int(f.has_xbrl),
            )
            for f in filings
        ],
    )
    conn.commit()
    return conn.total_changes - before


def save_classifications(conn: sqlite3.Connection, items: dict[str, Classification]) -> None:
    conn.executemany(
        "UPDATE filings SET category=?, subtype=?, noise=?, classified_by=?, confidence=?"
        " WHERE seq_id=?",
        [
            (c.category, c.subtype, int(c.noise), c.by, c.confidence, sid)
            for sid, c in items.items()
        ],
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


def default_classified_filings(conn: sqlite3.Connection) -> list[Filing]:
    """Filings that got the fallback default (rules missed, no usable LLM answer)."""
    rows = conn.execute(
        "SELECT * FROM filings WHERE classified_by = 'default' ORDER BY filed_at, seq_id"
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


def latest_filed_at(conn: sqlite3.Connection, symbols: list[str]) -> datetime | None:
    """When the newest stored filing for any of the symbols was filed, or None."""
    if not symbols:
        return None
    marks = ",".join("?" * len(symbols))
    (newest,) = conn.execute(
        f"SELECT MAX(filed_at) FROM filings WHERE symbol IN ({marks})", symbols
    ).fetchone()
    return datetime.fromisoformat(newest) if newest else None


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
            symbol=r["symbol"],
            date=date.fromisoformat(r["date"]),
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
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


def get_filing(
    conn: sqlite3.Connection, seq_id: str
) -> tuple[Filing, Classification | None] | None:
    row = conn.execute("SELECT * FROM filings WHERE seq_id=?", (seq_id,)).fetchone()
    return (_filing(row), _classification(row)) if row else None


def upsert_financials(
    conn: sqlite3.Connection, q: QuarterFinancials, filed_at: datetime, xbrl_url: str
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO financials
           (symbol, period_end, basis, format, period_start, audited, filed_at,
            xbrl_url, facts_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            q.symbol,
            q.period_end.isoformat(),
            q.basis,
            q.format,
            q.period_start.isoformat(),
            None if q.audited is None else int(q.audited),
            _ts(filed_at),
            xbrl_url,
            json.dumps(q.facts),
        ),
    )
    conn.commit()


def get_financials(
    conn: sqlite3.Connection, symbol: str, period_end: date, basis: str
) -> tuple[QuarterFinancials, datetime, str] | None:
    r = conn.execute(
        "SELECT * FROM financials WHERE symbol = ? AND period_end = ? AND basis = ?",
        (symbol, period_end.isoformat(), basis),
    ).fetchone()
    if r is None:
        return None
    q = QuarterFinancials(
        symbol=r["symbol"],
        period_start=date.fromisoformat(r["period_start"]),
        period_end=date.fromisoformat(r["period_end"]),
        basis=r["basis"],
        format=r["format"],
        audited=None if r["audited"] is None else bool(r["audited"]),
        facts=json.loads(r["facts_json"]),
    )
    return q, datetime.fromisoformat(r["filed_at"]), r["xbrl_url"]


def stored_financials_urls(conn: sqlite3.Connection, symbol: str) -> set[str]:
    rows = conn.execute("SELECT xbrl_url FROM financials WHERE symbol = ?", (symbol,))
    return {r["xbrl_url"] for r in rows}


def latest_financials(conn: sqlite3.Connection, symbol: str) -> tuple[date, str, datetime] | None:
    """(period_end, basis, filed_at) of the newest period; consolidated preferred."""
    r = conn.execute(
        """SELECT period_end, basis, filed_at FROM financials WHERE symbol = ?
           ORDER BY period_end DESC, basis = 'consolidated' DESC LIMIT 1""",
        (symbol,),
    ).fetchone()
    if r is None:
        return None
    return (
        date.fromisoformat(r["period_end"]),
        r["basis"],
        datetime.fromisoformat(r["filed_at"]),
    )


def get_doc_text_cached(conn: sqlite3.Connection, url: str) -> str | None:
    """Cached PDF text for url; None if never fetched ("" is a valid cached value)."""
    r = conn.execute("SELECT text FROM doc_text WHERE url = ?", (url,)).fetchone()
    return None if r is None else r["text"]


def save_doc_text(conn: sqlite3.Connection, url: str, text: str) -> None:
    conn.execute(
        """INSERT INTO doc_text (url, fetched_at, chars, text) VALUES (?, ?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET fetched_at = excluded.fetched_at,
               chars = excluded.chars, text = excluded.text""",
        (url, _ts(datetime.now(IST)), len(text), text),
    )
    conn.commit()


def get_doc_pages(conn: sqlite3.Connection, url: str) -> list[str] | None:
    """Cached page texts ordered by page; None if never cached, [] for the empty sentinel."""
    rows = conn.execute("SELECT page, text FROM doc_pages WHERE url = ? ORDER BY page", (url,))
    rows = rows.fetchall()
    if not rows:
        return None
    return [r["text"] for r in rows if r["page"] > 0]


def save_doc_pages(conn: sqlite3.Connection, url: str, pages: list[str]) -> None:
    """Cache pages 1..n; an empty list stores the page-0 sentinel so it is not refetched."""
    rows = [(url, i, t) for i, t in enumerate(pages, 1)] or [(url, 0, "")]
    conn.executemany("INSERT OR REPLACE INTO doc_pages (url, page, text) VALUES (?,?,?)", rows)
    conn.commit()


def save_enrichment(
    conn: sqlite3.Connection, seq_id: str, kind: str, payload: dict, model: str | None
) -> None:
    conn.execute(
        """INSERT INTO enrichments (seq_id, kind, payload_json, model, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(seq_id, kind) DO UPDATE SET payload_json = excluded.payload_json,
               model = excluded.model, created_at = excluded.created_at""",
        (seq_id, kind, json.dumps(payload), model, _ts(datetime.now(IST))),
    )
    conn.commit()


def get_enrichments(conn: sqlite3.Connection, seq_ids: list[str], kind: str) -> dict[str, dict]:
    """Stored payloads of the given kind, keyed by seq_id.

    Missing ids are absent, and so are rows whose payload is not a JSON object: the digest
    reads these at request time and must not fail on one corrupt row.
    """
    if not seq_ids:
        return {}
    marks = ",".join("?" * len(seq_ids))
    rows = conn.execute(
        f"SELECT seq_id, payload_json FROM enrichments WHERE kind = ? AND seq_id IN ({marks})",
        [kind, *seq_ids],
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
        except (TypeError, ValueError):
            payload = None
        if not isinstance(payload, dict):
            log.warning("skipping unreadable %s enrichment for %s", kind, r["seq_id"])
            continue
        out[r["seq_id"]] = payload
    return out


def filings_missing_enrichment(
    conn: sqlite3.Connection, kind: str, categories: set[str], start: datetime
) -> list[tuple[Filing, Classification]]:
    """Classified filings filed at or after start, in categories, with no enrichment of kind."""
    if not categories:
        return []
    cats = sorted(categories)
    marks = ",".join("?" * len(cats))
    rows = conn.execute(
        f"""SELECT f.* FROM filings f
            WHERE f.filed_at >= ? AND f.category IN ({marks})
              AND NOT EXISTS (SELECT 1 FROM enrichments e
                              WHERE e.seq_id = f.seq_id AND e.kind = ?)
            ORDER BY f.filed_at, f.seq_id""",
        [_ts(start), *cats, kind],
    ).fetchall()
    out: list[tuple[Filing, Classification]] = []
    for r in rows:
        cls = _classification(r)
        if cls is not None:
            out.append((_filing(r), cls))
    return out


def save_dossier(conn: sqlite3.Connection, dossier: Dossier) -> None:
    """Store the whole dossier, source pages included (citation excerpts are served from it)."""
    conn.execute(
        "INSERT OR REPLACE INTO dossiers (symbol, built_at, payload_json) VALUES (?,?,?)",
        (dossier.symbol, _ts(dossier.built_at), dossier.model_dump_json()),
    )
    conn.commit()


def get_dossier(conn: sqlite3.Connection, symbol: str) -> Dossier | None:
    r = conn.execute("SELECT payload_json FROM dossiers WHERE symbol = ?", (symbol,)).fetchone()
    return None if r is None else Dossier.model_validate_json(r["payload_json"])


def list_dossiers(conn: sqlite3.Connection) -> list[Dossier]:
    rows = conn.execute("SELECT payload_json FROM dossiers ORDER BY symbol").fetchall()
    return [Dossier.model_validate_json(r["payload_json"]) for r in rows]
