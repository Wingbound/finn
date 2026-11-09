"""Check our XBRL-derived results numbers against screener.in's quarterly table.

Run: uv run python scripts/eval_results.py --offline        (fixtures, no network)
     uv run python scripts/eval_results.py [--db PATH]      (stored cards vs live screener)

A pair is compared only when the screener page's basis equals the card's basis. A pair
matches when it is within 1% relative or INR 1 crore absolute, whichever is more lenient.
Reports; never gates (exit code 0).
"""

from __future__ import annotations

import argparse
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from finn import db
from finn.config import get_settings
from finn.enrich.results import card_for
from finn.ingest.screener import fetch_quarters, parse_quarters
from finn.ingest.xbrl import parse_xbrl
from finn.portfolio import load_portfolio

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
CRORE = 1e7
ASSOC = "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod"

# format -> (our metric key, screener row label)
PAIRS: dict[str, list[tuple[str, str]]] = {
    "indas": [
        ("revenue", "Sales"),
        ("ebitda", "Operating Profit"),
        ("pbt+assoc", "Profit before tax"),
        ("pat", "Net Profit"),
    ],
    "bank": [
        ("interest_earned", "Revenue"),
        ("pbt", "Profit before tax"),
        ("pat", "Net Profit"),
    ],
    "nbfc": [("revenue", "Revenue"), ("pbt", "Profit before tax"), ("pat", "Net Profit")],
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class Row:
    symbol: str
    basis: str
    metric: str
    ours: float | None = None
    screener: float | None = None
    diff_pct: float | None = None
    match: bool | None = None  # None = not compared
    note: str = ""


def within(ours: float, theirs: float) -> bool:
    return abs(ours - theirs) <= max(0.01 * abs(theirs), 1.0)


def compare(conn: sqlite3.Connection, symbol: str, page_basis: str, page_html: str) -> list[Row]:
    got = card_for(conn, symbol)
    if got is None:
        return [Row(symbol, "-", "-", note="skipped: no stored card")]
    card, _ = got
    if card.basis != page_basis:
        return [Row(symbol, card.basis, "-", note="skipped: basis mismatch")]
    col = f"{MONTHS[card.period_end.month - 1]} {card.period_end.year}"
    sc = parse_quarters(page_html).get(col)
    if not sc:
        return [Row(symbol, card.basis, "-", note=f"skipped: no screener column {col}")]
    ours = {m.key: m.value for m in card.metrics}
    if card.format == "indas":
        q = db.get_financials(conn, symbol, card.period_end, card.basis)
        pbt = ours.get("pbt")
        assoc = q[0].facts.get(ASSOC, 0.0) if q else 0.0
        ours["pbt+assoc"] = None if pbt is None else pbt + assoc / CRORE
    rows = []
    for key, label in PAIRS[card.format]:
        o, s = ours.get(key), sc.get(label)
        if o is None or s is None:
            rows.append(Row(symbol, card.basis, key, o, s, note="missing value"))
            continue
        diff = (o - s) / abs(s) * 100 if s else None
        rows.append(Row(symbol, card.basis, key, o, s, diff, within(o, s)))
    return rows


def _fixture_conn() -> sqlite3.Connection:
    from datetime import datetime

    from finn.models import IST

    conn = db.connect(Path(tempfile.mkdtemp()) / "eval.sqlite")
    db.init_db(conn)
    for f in sorted((FIX / "xbrl").glob("*.xml")):
        q = parse_xbrl(f.read_bytes())
        q = q.model_copy(update={"symbol": f.name.split("_")[0]})
        db.upsert_financials(conn, q, datetime.now(IST), f"fixture:{f.name}")
    return conn


def evaluate_offline() -> list[Row]:
    conn = _fixture_conn()
    rows: list[Row] = []
    for sym in ("TATASTEEL", "IDFCFIRSTB", "BAJFINANCE"):
        html = (FIX / "screener" / f"{sym}_consolidated_quarters.html").read_text()
        rows += compare(conn, sym, "consolidated", html)
    conn.close()
    return rows


def evaluate_live(conn: sqlite3.Connection) -> list[Row]:
    rows: list[Row] = []
    for h in load_portfolio():
        latest = db.latest_financials(conn, h.symbol)
        if latest is None:
            rows.append(Row(h.symbol, "-", "-", note="skipped: no stored card"))
            continue
        basis = latest[1]
        try:
            html = fetch_quarters(h.symbol, basis)
        except Exception as e:  # noqa: BLE001 - report and carry on
            rows.append(Row(h.symbol, basis, "-", note=f"skipped: fetch failed: {e}"))
            continue
        rows += compare(conn, h.symbol, basis, html)
    return rows


def _fmt(x: float | None, nd: int = 2) -> str:
    return "" if x is None else f"{x:,.{nd}f}"


def render(rows: list[Row]) -> str:
    lines = [
        "| symbol | basis | metric | ours | screener | diff % | match |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        mark = r.note if r.match is None else ("yes" if r.match else "NO")
        lines.append(
            f"| {r.symbol} | {r.basis} | {r.metric} | {_fmt(r.ours)} | {_fmt(r.screener)} "
            f"| {_fmt(r.diff_pct)} | {mark} |"
        )
    tally: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        if r.match is not None:
            tally[r.metric].append(r.match)
    lines += ["", "Match rate per metric:", ""]
    for metric, hits in sorted(tally.items()):
        lines.append(f"- {metric}: {sum(hits)}/{len(hits)}")
    if not tally:
        lines.append("- no pairs compared")
    misses = [r for r in rows if r.match is False]
    lines += ["", "Misses:", ""]
    lines += [f"- {r.symbol} {r.metric}: ours {_fmt(r.ours)} vs {_fmt(r.screener)}" for r in misses]
    if not misses:
        lines.append("- none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="use the fixtures, no network")
    parser.add_argument("--db", type=Path, help="SQLite file (default: DB_PATH)")
    args = parser.parse_args(argv)
    if args.offline:
        rows = evaluate_offline()
    else:
        conn = db.connect(args.db or get_settings().db_path)
        try:
            rows = evaluate_live(conn)
        finally:
            conn.close()
    print(render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
