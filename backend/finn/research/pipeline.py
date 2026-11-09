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
# A note containing any of these means part of the dossier is missing for a transient reason
# (model down, a bug, the deadline): such a build never replaces a complete stored one.
DEGRADED_MARKERS = (
    "model unavailable",
    "could not be built",
    "could not be read",
    "skipped: build deadline reached",
)


def is_degraded(d: Dossier) -> bool:
    return any(m in n for n in d.notes for m in DEGRADED_MARKERS)


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

    def failed(what: str, e: Exception, verb: str = "built") -> None:
        log.warning("%s failed for %s: %s: %s", what, symbol, type(e).__name__, e)
        notes.append(f"{what} could not be {verb} (internal error)")

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
        failed("Financials", e)

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
        failed("Sources", e)

    promises: list[Promise] = []
    transcripts = [s for s in sources if s.kind == "transcript"]
    unread = 0  # transcripts whose guidance the model did not return
    for src in transcripts:
        if late(f"Guidance from {src.title}"):
            continue
        progress(f"Extracting guidance from {src.title}")
        got: list[str] = []
        try:
            promises.extend(extract_promises(router, src, guard, got))
        except Exception as e:  # noqa: BLE001
            failed(f"Guidance from {src.title}", e, "read")
        unread += bool(got)
        notes.extend(got)

    ledger = None
    if sources and not late("Ledger"):
        progress(f"Checking delivery on {len(promises)} promises")
        try:
            ledger = build_ledger(router, promises, sources, quarters or {}, pl or {}, notes=notes)
        except Exception as e:  # noqa: BLE001
            failed("Ledger", e)
    if ledger is not None and not ledger.rows and len(transcripts) >= 2:
        n = len(transcripts)
        ledger.note = (
            f"Guidance could not be read from {unread} of {n} calls (model unavailable)"
            if unread
            else f"No verifiable forward-looking guidance found in {n} calls"
        )

    snap = None
    bull: list[Point] = []
    bear: list[Point] = []
    if sources:
        progress("Writing snapshot and bull/bear")
        if not late("Snapshot"):
            try:
                snap = snapshot(router, sources, guard, notes)
            except Exception as e:  # noqa: BLE001
                failed("Snapshot", e)
        if ledger is None or traj is None or health is None:
            notes.append("Bull/bear skipped: ledger or financials unavailable")
        elif not late("Bull/bear"):
            try:
                bull, bear = bull_bear(router, sources, ledger, traj, health, guard, notes)
            except Exception as e:  # noqa: BLE001
                failed("Bull/bear", e)
    else:
        notes.append("Snapshot, ledger and bull/bear skipped: no sources")

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
