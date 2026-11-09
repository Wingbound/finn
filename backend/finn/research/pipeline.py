"""The dossier pipeline: screener tables, sources, guidance, ledger, snapshot, bull/bear."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime

from finn.ingest import screener
from finn.models import IST, Dossier, Point, Promise
from finn.research.docs import MAX_TRANSCRIPTS, DocClient, collect_sources
from finn.research.financials import balance_sheet_health, is_lender, trajectory
from finn.research.guidance import extract_promises
from finn.research.ledger import build_ledger
from finn.research.synthesis import bull_bear, snapshot

log = logging.getLogger(__name__)

COST_KEYS = ("calls", "cached", "input_tokens", "output_tokens", "usd_list_price")


def build_dossier(
    conn: sqlite3.Connection,
    symbol: str,
    router,
    *,
    screener_client=None,
    doc_client=None,
    progress: Callable[[str], None] = lambda m: None,
    deadline_s: float = 240,
    now: Callable[[], float] = time.monotonic,
) -> Dossier:
    """Build a dossier. ScreenerError (unknown symbol) propagates; every other failure inside
    a stage becomes a note and the build carries on."""
    symbol = symbol.upper()
    t0 = now()
    before = router.stats() if hasattr(router, "stats") else {}
    notes: list[str] = []
    guard = {"promises_proposed": 0, "promises_kept": 0, "points_proposed": 0, "points_kept": 0}

    progress(f"Resolving {symbol} on screener")
    html, basis = screener.fetch_company(symbol, screener_client)
    name = screener.parse_name(html)

    def late(stage: str) -> bool:
        if now() - t0 > deadline_s:
            notes.append(f"{stage} skipped: build deadline reached")
            return True
        return False

    def failed(stage: str, e: Exception) -> None:
        log.warning("%s failed for %s: %s", stage, symbol, e)
        notes.append(f"{stage} failed: {type(e).__name__}")

    pl = quarters = None
    traj = health = None
    try:
        pl = screener.parse_table(html, "profit-loss")
        bs = screener.parse_table(html, "balance-sheet")
        cf = screener.parse_table(html, "cash-flow")
        ratios = screener.parse_table(html, "ratios")
        quarters = screener.parse_table(html, "quarters", keep_pct=False)
        traj = trajectory(pl)
        health = balance_sheet_health(pl, bs, cf, ratios, is_lender(pl))
    except Exception as e:  # noqa: BLE001
        failed("financials", e)

    sources = []
    documents: dict = {}
    try:
        documents = screener.parse_documents(html)
        n_t = sum(1 for c in documents.get("concalls", []) if c.get("transcript_url"))
        n_ar = len(documents.get("annual_reports", []))
        ar_part = f"{n_ar} annual report(s) (reading the latest)" if n_ar else "no annual report"
        progress(
            f"Found {n_t} transcripts (reading the latest {min(n_t, MAX_TRANSCRIPTS)}) "
            f"and {ar_part}"
        )
        own = doc_client is None
        client = doc_client or DocClient()
        try:
            sources, src_notes = collect_sources(conn, client, documents, progress=progress)
        finally:
            if own:
                client.close()
        notes.extend(src_notes)
    except Exception as e:  # noqa: BLE001
        failed("sources", e)

    promises: list[Promise] = []
    for src in sources:
        if src.kind != "transcript":
            continue
        if late(f"guidance ({src.id})"):
            continue
        progress(f"Extracting guidance from {src.title}")
        try:
            promises.extend(extract_promises(router, src, guard))
        except Exception as e:  # noqa: BLE001
            failed(f"guidance ({src.id})", e)

    ledger = None
    if sources and not late("ledger"):
        progress(f"Checking delivery on {len(promises)} promises")
        try:
            ledger = build_ledger(router, promises, sources, quarters or {}, pl or {})
        except Exception as e:  # noqa: BLE001
            failed("ledger", e)

    snap = None
    bull: list[Point] = []
    bear: list[Point] = []
    if sources:
        progress("Writing snapshot and bull/bear")
        if not late("snapshot"):
            try:
                snap = snapshot(router, sources, guard)
            except Exception as e:  # noqa: BLE001
                failed("snapshot", e)
        if ledger is None or traj is None or health is None:
            notes.append("bull/bear skipped: ledger or financials unavailable")
        elif not late("bull/bear"):
            try:
                bull, bear = bull_bear(router, sources, ledger, traj, health, guard)
            except Exception as e:  # noqa: BLE001
                failed("bull/bear", e)
    else:
        notes.append("snapshot, ledger and bull/bear skipped: no sources")

    after = router.stats() if hasattr(router, "stats") else {}
    cost = {k: after.get(k, 0) - before.get(k, 0) for k in COST_KEYS}
    cost["usd_list_price"] = round(cost["usd_list_price"], 6)
    secs = now() - t0
    progress(f"Done in {secs:.0f}s")
    return Dossier(
        symbol=symbol,
        name=name,
        basis=basis,
        built_at=datetime.now(IST),
        sources=sources,
        ledger=ledger,
        snapshot=snap,
        trajectory=traj,
        health=health,
        bull=bull,
        bear=bear,
        notes=notes,
        cost=cost,
        build_seconds=round(secs, 1),
        guard=guard,
    )
