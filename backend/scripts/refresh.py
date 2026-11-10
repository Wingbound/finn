"""Refresh filings, EOD prices and classifications into a FINN SQLite store.

Run: uv run python scripts/refresh.py --days 30 [--no-llm] [--out seed/finn.sqlite]

An unreachable NSE or Yahoo, a symbol either one fails on, or a crash in one stage is
reported in the summary's `errors` and the run carries on with what it has (exit code 1).
A run that ingests no filings and no prices exits 2, and a crash exits 4; both leave the store
untouched.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from finn import db
from finn.classify.pipeline import classify_pending
from finn.config import chain_for, get_settings
from finn.enrich.brief import enrich_briefs
from finn.enrich.people import enrich_people
from finn.enrich.results import ingest_financials
from finn.ingest.nse import NSEClient, ingest_filings
from finn.ingest.nse_mcp import fetch_nse_eod
from finn.ingest.prices import fetch_eod
from finn.llm import LLMRouter
from finn.llm.providers import PROVIDERS
from finn.models import IST, Rules
from finn.portfolio import load_portfolio

_LLM_TASKS = ("classify", "bio", "oneliner")  # the tasks a refresh sends to an LLM


def _router(conn: sqlite3.Connection, use_llm: bool) -> LLMRouter | None:
    """A router when any provider on a refresh task's chain has a key; else None (rules only)."""
    if not use_llm:
        return None
    settings = get_settings()
    providers = {p for task in _LLM_TASKS for p, _model in chain_for(task, settings)}
    if not any(settings.api_key(PROVIDERS[p][2]) for p in providers):
        keys = ", ".join(sorted(PROVIDERS[p][3] for p in providers))
        print(f"note: no LLM key set ({keys}); rules only, no enrichment (as with --no-llm)")
        return None
    return LLMRouter(conn, settings)


def _count(conn: sqlite3.Connection, where: str = "1") -> int:
    return conn.execute(f"SELECT COUNT(*) FROM filings WHERE {where}").fetchone()[0]


def _enrich_stage(name: str, run, enrich: dict[str, dict], errors: list[str]) -> None:
    try:
        res = run()
    except Exception as e:  # noqa: BLE001 - one stage failing must not block the next
        errors.append(f"{name}: {type(e).__name__}: {e}")
        print(f"{name} stage failed: {type(e).__name__}: {e}")
        return
    enrich[name] = {"done": res.done, "empty": res.empty, "failed": res.failed}
    errors += [f"{name}: {seq}: {why}" for seq, why in res.failed.items()]


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
    # NSE's own end-of-day data first; Yahoo only for the symbols NSE couldn't give.
    bars = []
    try:
        bars, nse_failed = fetch_nse_eod(holdings)
    except Exception as e:  # noqa: BLE001 - a broken NSE client must not stop the refresh
        bars, nse_failed = [], {h.symbol: f"{type(e).__name__}: {e}" for h in holdings}
    if nse_failed:
        print(f"NSE end-of-day unavailable for {len(nse_failed)} symbol(s); trying Yahoo")
    from_nse = {b.symbol for b in bars}
    rest = [h for h in holdings if h.symbol not in from_nse]
    fetched_at = datetime.now(IST)
    if rest:
        try:
            bars += fetch_eod(rest)
            fetched_at = datetime.now(IST)
        except Exception as e:  # noqa: BLE001 - yfinance raises assorted network/parse types
            errors.append(f"prices: {type(e).__name__}: {e}")
            print(f"price fetch failed, keeping existing prices: {type(e).__name__}: {e}")
        else:
            if not bars:
                errors.append("prices: no bars returned")
                print("price fetch returned no bars, keeping existing prices")
    priced = {b.symbol for b in bars}
    from_yahoo = priced - from_nse
    price_sources = {"nse": len(from_nse), "yahoo": len(from_yahoo)}
    prices_missing = [h.symbol for h in holdings if h.symbol not in priced]
    if bars:
        db.upsert_prices(conn, bars)
        db.set_meta(conn, "prices_as_of", fetched_at.isoformat())
        if not from_yahoo:
            source = "NSE end-of-day"
        elif not from_nse:
            source = "Yahoo end-of-day"
        else:
            source = f"NSE end-of-day (Yahoo for {len(from_yahoo)})"
        db.set_meta(conn, "prices_source", source)
        if prices_missing:
            errors.append(f"prices: no bars for {', '.join(prices_missing)}")

    router = _router(conn, use_llm)
    # Classify first: the enrichers select filings by their stored category.
    classify = classify_pending(conn, router)
    since = now - timedelta(days=days)
    financials = {"fetched": 0, "skipped": 0, "failed": {}}
    enrich: dict[str, dict] = {}
    try:
        client = NSEClient()
        try:
            fin = ingest_financials(conn, client, [h.symbol for h in holdings])
            financials = {"fetched": fin.fetched, "skipped": fin.skipped, "failed": fin.failed}
            errors += [f"financials: {sym}: {why}" for sym, why in fin.failed.items()]
            if router is not None:
                _enrich_stage(
                    "people", lambda: enrich_people(conn, client, router, since), enrich, errors
                )
                _enrich_stage(
                    "briefs",
                    lambda: enrich_briefs(conn, client, router, since, Rules().categories),
                    enrich,
                    errors,
                )
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001 - enrichment must never block the snapshot
        errors.append(f"financials: {type(e).__name__}: {e}")
        print(f"financials/enrichment stage failed: {type(e).__name__}: {e}")

    summary = {
        "filings_new": filings_new,
        "filings_skipped": filings_skipped,
        "price_bars": len(bars),
        "price_symbols": len(priced),
        "price_sources": price_sources,
        "prices_missing": prices_missing,
        "classify": classify,
        "filings_total": _count(conn),
        "unclassified_left": _count(conn, "category IS NULL"),
        "financials": financials,
        "enrich": enrich,
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

    target = Path(args.out or get_settings().db_path)
    # Work on a copy: a run that ingests nothing (exit 2) must leave the snapshot as it was,
    # so a scheduled job never commits a store gutted by an outage.
    work = target.with_name(f"{target.name}.refresh-tmp")
    _discard(work)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        src = sqlite3.connect(target)
        dst = sqlite3.connect(work)
        src.backup(dst)
        src.close()
        dst.close()
    conn = db.connect(work)
    try:
        summary = refresh(conn, days=args.days, use_llm=not args.no_llm)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # fold the WAL in; file stands alone
        conn.execute("PRAGMA journal_mode=DELETE")
    except Exception as e:  # noqa: BLE001 - a crash must not read as "partial" (exit 1)
        conn.close()
        _discard(work)
        print(f"refresh crashed: {type(e).__name__}: {e}", file=sys.stderr)
        return CRASHED
    finally:
        conn.close()
    print(json.dumps(summary, indent=2))
    code = exit_code(summary)
    if code == 2:
        _discard(work)
        return 2
    for sidecar in ("-wal", "-shm"):
        Path(f"{target}{sidecar}").unlink(missing_ok=True)
    work.replace(target)
    _discard(work)
    return code


CRASHED = 4  # distinct from Python's own exit 1 for an uncaught exception


def exit_code(summary: dict) -> int:
    """0 clean; 1 partial (something failed, the store was still updated); 2 nothing ingested."""
    if not summary["errors"]:
        return 0
    nothing = summary.get("filings_new", 0) == 0 and summary.get("price_bars", 0) == 0
    return 2 if nothing else 1


def _discard(path: Path) -> None:
    for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm"), Path(f"{path}-journal")):
        p.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
