"""Re-verify stored research dossiers and report guard, ledger and cost figures.

Run: uv run python scripts/eval_research.py [--db PATH]

For every dossier: each citation (ledger promise and evidence, snapshot, bull, bear) is
re-located verbatim in its stored source pages and must land on the stored page; FACTS
citations must equal a line of the recomputed facts block. Expect 100%; every failure is a
bug and is listed. Reports; exit code is always 0.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from finn import db
from finn.config import get_settings
from finn.enrich.grounding import normalize
from finn.models import Citation, Dossier
from finn.research.cite import dossier_citations, locate
from finn.research.synthesis import facts_block

STATUSES = ("kept", "partly", "missed", "pending", "dropped")


@dataclass
class DossierEval:
    symbol: str
    total: int = 0
    verified: int = 0
    facts: int = 0
    failures: list[str] = field(default_factory=list)
    statuses: dict[str, int] = field(default_factory=dict)
    computed: int = 0
    judged: int = 0
    guard: dict = field(default_factory=dict)
    calls: int = 0
    usd: float = 0.0
    seconds: float = 0.0
    downgraded: dict = field(default_factory=dict)


def _facts_lines(d: Dossier) -> set[str]:
    if d.trajectory is None or d.health is None or d.ledger is None:
        return set()
    return {normalize(ln) for ln in facts_block(d.trajectory, d.health, d.ledger).splitlines()}


def _ok(c: Citation, by_id: dict, facts: set[str]) -> bool:
    if c.source_id == "FACTS":
        return c.page == 0 and normalize(c.quote) in facts
    src = by_id.get(c.source_id)
    if src is None:
        return False
    found = locate(c.quote, src, c.page)
    return found is not None and found.page == c.page


def evaluate_dossier(d: Dossier) -> DossierEval:
    r = DossierEval(d.symbol, guard=dict(d.guard))
    by_id = {s.id: s for s in d.sources}
    facts = _facts_lines(d)
    for fld, c in dossier_citations(d):
        r.total += 1
        r.facts += c.source_id == "FACTS"
        if _ok(c, by_id, facts):
            r.verified += 1
        else:
            r.failures.append(f"{d.symbol} | {fld} | {c.source_id} p{c.page} | {c.quote[:80]}")
    if d.ledger:
        r.statuses = {k: sum(1 for x in d.ledger.rows if x.status == k) for k in STATUSES}
        r.computed = sum(1 for x in d.ledger.rows if x.method == "computed")
        r.judged = sum(1 for x in d.ledger.rows if x.method == "judged")
    r.downgraded = dict(d.guard.get("verdicts_downgraded") or {})
    r.calls = int(d.cost.get("calls", 0))
    r.usd = float(d.cost.get("usd_list_price", 0.0))
    r.seconds = d.build_seconds
    return r


def evaluate(conn: sqlite3.Connection) -> list[DossierEval]:
    return [evaluate_dossier(d) for d in db.list_dossiers(conn)]


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "n/a"


def _drop(kept: int, proposed: int) -> str:
    return f"{100 * (1 - kept / proposed):.0f}%" if proposed else "n/a"


def render(results: list[DossierEval]) -> str:
    head = (
        "| Symbol | Citations verified | FACTS citations "
        "| Ledger (kept/partly/missed/pending/dropped) "
        "| Computed/judged | Promises kept/proposed | Promise drop | Points kept/proposed "
        "| Point drop | Calls | USD (list) | Seconds "
        "| Verdicts downgraded (period/restated/below) |"
    )
    lines = [head, "|" + "---|" * 13]
    tot = DossierEval("total")
    for r in results:
        g = r.guard
        pk, pp = g.get("promises_kept", 0), g.get("promises_proposed", 0)
        tk, tp = g.get("points_kept", 0), g.get("points_proposed", 0)
        lines.append(_row(r.symbol, r, pk, pp, tk, tp))
        tot.total += r.total
        tot.verified += r.verified
        tot.facts += r.facts
        tot.computed += r.computed
        tot.judged += r.judged
        tot.calls += r.calls
        tot.usd += r.usd
        tot.seconds += r.seconds
        for k, v in r.downgraded.items():
            tot.downgraded[k] = tot.downgraded.get(k, 0) + v
        for k, v in r.statuses.items():
            tot.statuses[k] = tot.statuses.get(k, 0) + v
        tot.guard = {
            k: tot.guard.get(k, 0) + g.get(k, 0)
            for k in ("promises_kept", "promises_proposed", "points_kept", "points_proposed")
        }
    g = tot.guard
    lines.append(
        _row(
            "total",
            tot,
            g.get("promises_kept", 0),
            g.get("promises_proposed", 0),
            g.get("points_kept", 0),
            g.get("points_proposed", 0),
        )
    )
    fails = [f for r in results for f in r.failures]
    lines.append("")
    if fails:
        lines.append(f"Citation failures ({len(fails)}), symbol | field | source p | quote:")
        lines.extend(f"- {f}" for f in fails)
    else:
        lines.append("Citation failures: none")
    return "\n".join(lines)


def _row(label: str, r: DossierEval, pk: int, pp: int, tk: int, tp: int) -> str:
    st = "/".join(str(r.statuses.get(k, 0)) for k in STATUSES)
    dg = "/".join(str(r.downgraded.get(k, 0)) for k in ("other_period", "restated", "below_target"))
    return (
        f"| {label} | {r.verified}/{r.total} ({_pct(r.verified, r.total)}) | {r.facts} | {st} "
        f"| {r.computed}/{r.judged} | {pk}/{pp} | {_drop(pk, pp)} | {tk}/{tp} | {_drop(tk, tp)} "
        f"| {r.calls} | {r.usd:.4f} | {r.seconds:.1f} | {dg} |"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: DB_PATH)")
    args = ap.parse_args(argv)
    path = args.db or get_settings().db_path
    conn = db.connect(path)
    try:
        db.init_db(conn)
        print(render(evaluate(conn)))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
