"""Refresh filings, EOD prices and classifications into a FINN SQLite store.

Run: uv run python scripts/refresh.py --days 30 [--no-llm] [--out seed/finn.sqlite]

An unreachable NSE or Yahoo, a symbol either one fails on, or a crash in one stage is
reported in the summary's `errors` and the run carries on with what it has (exit code 1).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from finn import db
from finn.classify.pipeline import classify_pending
from finn.config import get_settings, route_for
from finn.ingest.nse import NSEClient, ingest_filings
from finn.ingest.prices import fetch_eod
from finn.llm import LLMRouter
from finn.llm.providers import PROVIDERS
from finn.models import IST
from finn.portfolio import load_portfolio


def _router(conn: sqlite3.Connection, use_llm: bool) -> LLMRouter | None:
    if not use_llm:
        return None
    settings = get_settings()
    provider, _model = route_for("classify", settings)
    _call, _parse, key_attr, key_name = PROVIDERS[provider]
    if not getattr(settings, key_attr):
        print(f"note: {key_name} is empty; classifying with rules only (as with --no-llm)")
        return None
    return LLMRouter(conn, settings)


def _count(conn: sqlite3.Connection, where: str = "1") -> int:
    return conn.execute(f"SELECT COUNT(*) FROM filings WHERE {where}").fetchone()[0]


def refresh(conn: sqlite3.Connection, days: int = 30, use_llm: bool = True) -> dict:
    """Ingest the last `days` of filings and ~3 months of prices, then classify. Returns counts."""
    db.init_db(conn)
    holdings = load_portfolio()
    now = datetime.now(IST)
    errors: list[str] = []

    filings_new = filings_skipped = 0
    try:
        client = NSEClient()
        try:
            ingest = ingest_filings(
                conn,
                client,
                [h.symbol for h in holdings],
                (now - timedelta(days=days)).date(),
                now.date(),
            )
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001 - a filings crash must not block the price stage
        errors.append(f"filings: {type(e).__name__}: {e}")
        print(f"filing ingest failed, keeping existing filings: {type(e).__name__}: {e}")
    else:
        filings_new, filings_skipped = ingest.added, ingest.skipped
        errors += [f"filings: {why}" for why in ingest.failed.values()]
        if ingest.failed:
            print(f"NSE unavailable for {', '.join(ingest.failed)}; keeping their stored filings")

    # Prices always span ~3 months: the alert engine needs a 20-session volume baseline.
    bars = []
    try:
        bars = fetch_eod(holdings)
        fetched_at = datetime.now(IST)
    except Exception as e:  # noqa: BLE001 - yfinance raises assorted network/parse types
        errors.append(f"prices: {type(e).__name__}: {e}")
        print(f"price fetch failed, keeping existing prices: {type(e).__name__}: {e}")
    else:
        if not bars:
            errors.append("prices: no bars returned")
            print("price fetch returned no bars, keeping existing prices")
    priced = {b.symbol for b in bars}
    prices_missing = [h.symbol for h in holdings if h.symbol not in priced]
    if bars:
        db.upsert_prices(conn, bars)
        db.set_meta(conn, "prices_as_of", fetched_at.isoformat())
        if prices_missing:
            errors.append(f"prices: no bars for {', '.join(prices_missing)}")

    router = _router(conn, use_llm)
    summary = {
        "filings_new": filings_new,
        "filings_skipped": filings_skipped,
        "price_bars": len(bars),
        "price_symbols": len(priced),
        "prices_missing": prices_missing,
        "classify": classify_pending(conn, router),
        "filings_total": _count(conn),
        "unclassified_left": _count(conn, "category IS NULL"),
        "errors": errors,
    }
    if router is not None:
        summary["llm"] = router.stats()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30, help="filing window in days")
    parser.add_argument("--no-llm", action="store_true", help="rules only; misses -> unclassified")
    parser.add_argument("--out", type=Path, help="SQLite file to write (default: DB_PATH)")
    args = parser.parse_args(argv)

    conn = db.connect(args.out or get_settings().db_path)
    try:
        summary = refresh(conn, days=args.days, use_llm=not args.no_llm)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # fold the WAL in; file stands alone
    finally:
        conn.close()
    print(json.dumps(summary, indent=2))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
