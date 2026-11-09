"""Cited snapshot and bull/bear points. Every point carries a verbatim quote or is dropped."""

from __future__ import annotations

from typing import Any

from finn.enrich.grounding import normalize, numbers_grounded
from finn.llm.providers import LLMError
from finn.models import (
    BalanceSheetHealth,
    Citation,
    Ledger,
    Point,
    Snapshot,
    Source,
    Trajectory,
)
from finn.research.cite import locate, tagged_text

MAX_WORDS = 30
AR_PAGES = 10
T1_SNAPSHOT_PAGES = 4

_ITEM = (
    '{"text": "<one plain sentence, at most 30 words>", "quote": "<verbatim sentence copied '
    'from the sources, at least 6 words>", "source_id": "<id of that source>", '
    '"page": <page number from the [[pN]] tag>}'
)
SNAPSHOT_SYSTEM = f"""You describe what a listed company does, for an investor, using only the \
sources below. Write 2 to 4 points covering its business and segments. Each point is one \
plain sentence of at most 30 words and must be backed by a verbatim quote from the sources. \
Any number in your sentence must appear in the quote. Do not add anything the quote does not \
say. Reply as JSON: {{"summary": [{_ITEM}]}}"""
BULL_BEAR_SYSTEM = f"""You write the bull case and the bear case for a listed company, using \
only the FACTS, the promise ledger lines and the sources below. Give up to 3 bull points and \
up to 3 bear points. Each point is one plain sentence of at most 30 words, backed by a \
verbatim quote: cite a transcript or annual report page, or a FACTS line for computed \
financials (source_id FACTS, page 0, quote copied from that line). Any number in your sentence must appear in the quote or in \
the FACTS. Do not predict prices or recommend buying or selling. Reply as JSON: \
{{"bull": [{_ITEM}], "bear": [{_ITEM}]}}"""


def facts_block(trajectory: Trajectory, health: BalanceSheetHealth, ledger: Ledger) -> str:
    lines: list[str] = []
    t, h = trajectory, health
    if t.revenue_cagr_pct is not None:
        span = f" ({t.years[0]}–{t.years[-1]})" if t.years else ""
        lines.append(f"Revenue CAGR{span}: {t.revenue_cagr_pct:.1f}%")
    if t.pat_cagr_pct is not None:
        lines.append(f"Net profit CAGR: {t.pat_cagr_pct:.1f}%")
    if t.margin_change_bps is not None:
        lines.append(f"Operating margin change: {t.margin_change_bps:+d} bps")
    if h.debt_to_equity is not None:
        lines.append(f"Debt to equity: {h.debt_to_equity:g}")
    if h.cfo_to_pat_3y is not None:
        lines.append(f"CFO/PAT (3y): {h.cfo_to_pat_3y:g}")
    if h.fcf_3y_cr is not None:
        lines.append(f"Free cash flow (3y): ₹{h.fcf_3y_cr:,.0f} cr")
    if h.working_capital_days is not None:
        lines.append(f"Working capital days: {h.working_capital_days:g}")
    if h.roce_pct is not None:
        lines.append(f"ROCE: {h.roce_pct:.1f}%")
    lines.extend(f.text for f in h.flags)
    c = ledger.counts
    if c:
        cred = (
            f" (credibility {ledger.credibility_pct:g}%)"
            if ledger.credibility_pct is not None
            else ""
        )
        counts = ", ".join(
            f"{c.get(k, 0)} {k}" for k in ("kept", "partly", "missed", "pending", "dropped")
        )
        lines.append(f"Promise ledger: {counts}{cred}")
    return "\n".join(lines)


def _head(src: Source, n: int) -> Source:
    return src.model_copy(update={"pages": src.pages[:n]})


def _ar(sources: list[Source]) -> Source | None:
    return next((s for s in sources if s.kind == "annual_report"), None)


def _t1(sources: list[Source]) -> Source | None:
    return next((s for s in sources if s.kind == "transcript"), None)


def _facts_cite(quote: str, facts: str) -> Citation | None:
    """The FACTS line equal to, or uniquely containing (3+ words), the quote."""
    q = normalize(quote)
    lines = [ln for ln in facts.splitlines() if ln.strip()]
    hit = [ln for ln in lines if normalize(ln) == q]
    if not hit and len(q.split()) >= 3:
        hit = [ln for ln in lines if q in normalize(ln)]
    return Citation(source_id="FACTS", page=0, quote=hit[0]) if len(hit) == 1 else None


def _validate(
    raw: Any,
    sources: dict[str, Source],
    facts: str,
    guard: dict | None,
    cap: int,
    allow_facts: bool = False,
) -> list[Point]:
    if not isinstance(raw, list):
        return []
    if guard is not None:
        guard["points_proposed"] = guard.get("points_proposed", 0) + len(raw)
    kept: list[Point] = []
    for it in raw:
        if len(kept) >= cap:
            break
        if not isinstance(it, dict):
            continue
        text, quote, sid, page = (it.get(k) for k in ("text", "quote", "source_id", "page"))
        if not (isinstance(text, str) and isinstance(quote, str) and isinstance(sid, str)):
            continue
        if not text.strip() or len(text.split()) > MAX_WORDS:
            continue
        if allow_facts and sid == "FACTS":
            cit = _facts_cite(quote, facts)
            if cit is None or not numbers_grounded(text, cit.quote):
                continue
        else:
            if sid not in sources:
                continue
            hint = page if isinstance(page, int) and not isinstance(page, bool) else None
            cit = locate(quote, sources[sid], hint)
            if cit is None or not numbers_grounded(text, quote + "\n" + facts):
                continue
        kept.append(Point(text=text.strip(), citation=cit))
    if guard is not None:
        guard["points_kept"] = guard.get("points_kept", 0) + len(kept)
    return kept


def _by_id(sources: list[Source]) -> dict[str, Source]:
    return {s.id: s for s in sources}


def snapshot(router, sources: list[Source], guard: dict | None = None) -> Snapshot | None:
    parts: list[str] = []
    ar, t1 = _ar(sources), _t1(sources)
    if ar:
        parts.append(f"SOURCE {ar.id} ({ar.title})\n{tagged_text(_head(ar, AR_PAGES))}")
    if t1:
        parts.append(f"SOURCE {t1.id} ({t1.title})\n{tagged_text(_head(t1, T1_SNAPSHOT_PAGES))}")
    if not parts:
        return None
    try:
        reply = router.complete_json("reason", SNAPSHOT_SYSTEM, "\n\n".join(parts))
    except LLMError:
        return None
    raw = reply.get("summary") if isinstance(reply, dict) else None
    points = _validate(raw, _by_id(sources), "", guard, 4)
    return Snapshot(summary=points) if points else None


def bull_bear(
    router,
    sources: list[Source],
    ledger: Ledger,
    trajectory: Trajectory,
    health: BalanceSheetHealth,
    guard: dict | None = None,
) -> tuple[list[Point], list[Point]]:
    facts = facts_block(trajectory, health, ledger)
    rows = [
        f'{r.status}: {r.promise.topic}, "{r.promise.citation.quote[:160]}" ({r.promise.made_in})'
        for r in ledger.rows
    ]
    ar, t1 = _ar(sources), _t1(sources)
    parts = [f"FACTS\n{facts}", "PROMISE LEDGER\n" + "\n".join(rows)]
    if t1:
        parts.append(f"SOURCE {t1.id} ({t1.title})\n{tagged_text(t1, 30_000)}")
    if ar:
        parts.append(f"SOURCE {ar.id} ({ar.title})\n{tagged_text(_head(ar, AR_PAGES))}")
    try:
        reply = router.complete_json("reason", BULL_BEAR_SYSTEM, "\n\n".join(parts))
    except LLMError:
        return [], []
    if not isinstance(reply, dict):
        return [], []
    by_id = _by_id(sources)
    bull = _validate(reply.get("bull"), by_id, facts, guard, 3, True)
    bear = _validate(reply.get("bear"), by_id, facts, guard, 3, True)
    return bull, bear
