"""Promise Ledger: grade each past promise, by code where numbers allow, else by evidence."""

from __future__ import annotations

import re
from typing import Literal

from finn.enrich.grounding import normalize
from finn.llm.providers import LLMError
from finn.models import Actual, Citation, Ledger, LedgerRow, Promise, Source, Status
from finn.research.cite import locate, tagged_text

STATUSES = ("kept", "partly", "missed", "pending", "dropped")
_COMPUTED = {"revenue_growth", "ebitda_margin", "pat_growth"}
_QTR = re.compile(r"\bQ([1-4])\s*FY\s*(\d{2}|\d{4})\b", re.IGNORECASE)
_FY = re.compile(r"\b(?:FY|fiscal)\s*(\d{2}|\d{4})\b", re.IGNORECASE)
_QMONTH = {1: "Jun", 2: "Sep", 3: "Dec", 4: "Mar"}
_NOT_ASSESSED = "Not assessed"
_NO_EVIDENCE = "No verifiable later evidence"
_NAMES = {
    "revenue_growth": "Revenue",
    "pat_growth": "Net profit",
    "ebitda_margin": "EBITDA margin",
}

JUDGE_EVIDENCE_CHARS = 200_000
Horizon = tuple[Literal["quarter", "fy"], str]


def _yy(s: str) -> int:
    return int(s) % 100


def _qkey(label: str | None) -> tuple[int, int] | None:
    """'Q2 FY27' -> (27, 2); None when empty or unparseable."""
    m = _QTR.search(label or "")
    return (_yy(m.group(2)), int(m.group(1))) if m else None


def _fy_of(made_in: str) -> int | None:
    k = _qkey(made_in)
    return k[0] if k else None


_H_QTR = re.compile(r"q([1-4])\s*fy\s*(\d{2}|\d{4})")
_H_FY = re.compile(r"(?:fy\s*|fiscal\s+(?:year\s+)?)(\d{2}|\d{4})")


def parse_horizon(horizon: str | None, made_in: str) -> Horizon | None:
    """Resolve only when the whole phrase is an explicit label or a known relative phrase."""
    low = re.sub(r"\s+", " ", (horizon or "").strip().lower())
    low = re.sub(r"^(in|for|during) ", "", low)
    m = _H_QTR.fullmatch(low)
    if m:
        return "quarter", f"Q{m.group(1)} FY{_yy(m.group(2)):02d}"
    m = _H_FY.fullmatch(low)
    if m:
        return "fy", f"FY{_yy(m.group(1)):02d}"
    k = _qkey(made_in)
    if k is None:
        return None
    yy, q = k
    if low in ("next quarter", "coming quarter"):
        return ("quarter", f"Q{q + 1} FY{yy:02d}") if q < 4 else ("quarter", f"Q1 FY{yy + 1:02d}")
    if low in ("next year", "next fiscal", "next financial year"):
        return "fy", f"FY{(yy + 1) % 100:02d}"
    if low in ("this year", "current year", "this fiscal", "this financial year"):
        return "fy", f"FY{yy:02d}"
    return None


def _column(kind: str, label: str, years_back: int = 0) -> str | None:
    if kind == "fy":
        m = re.fullmatch(r"FY(\d{2})", label)
        return f"Mar {2000 + int(m.group(1)) - years_back}" if m else None
    m = _QTR.fullmatch(label)
    if not m:
        return None
    q, yy = int(m.group(1)), _yy(m.group(2))
    year = 2000 + yy - (1 if q < 4 else 0) - years_back
    return f"{_QMONTH[q]} {year}"


def _get(table: dict, col: str | None, *labels: str) -> float | None:
    row = table.get(col) if col else None
    for label in labels:
        if row and label in row:
            return row[label]
    return None


def _fmt(x: float) -> str:
    return f"{x:g}"


_SEGMENT = re.compile(r"segment|division|vertical|business unit|subsidiary")
_LONG = re.compile(
    r"long[- ]term|medium[- ]term|aspiration|over the next few years"
    r"|\bfy\s?(?:20)?(?:28|29|30|31|32)\b|\b20(?:28|29|30|31|32)\b"
)
_NOT_DUE = "Target not yet due — tracking is not delivery"


def _grade(p: Promise, quarters: dict, annual: dict) -> tuple[Status, Actual | None, str] | None:
    if _SEGMENT.search(normalize(p.citation.quote)):
        return None
    if (
        p.kind != "quantitative"
        or p.metric not in _COMPUTED
        or p.unit != "%"
        or p.target_low is None
        or p.target_low <= 0
    ):
        return None
    hz = parse_horizon(p.horizon, p.made_in)
    if hz is None:
        return None
    kind, label = hz
    table = quarters if kind == "quarter" else annual
    col = _column(kind, label)
    if col is None:
        return None
    lo = p.target_low
    name = _NAMES[p.metric]
    if p.metric == "ebitda_margin":
        rev = _get(table, col, "Sales", "Revenue")
        op = _get(table, col, "Operating Profit", "Financing Profit")
        if col not in table:
            return "pending", None, ""
        if rev is None or op is None:
            return None
        if rev == 0:
            return None
        v = round(op / rev * 100, 2)
        status: Status = "kept" if v >= lo else "partly" if v >= lo - 1.0 else "missed"
        basis = f"operating profit / revenue from screener {kind} table"
        why = f"{name} was {v:.1f}% in {label} against a target of at least {_fmt(lo)}%"
    else:
        labels = ("Net Profit",) if p.metric == "pat_growth" else ("Sales", "Revenue")
        cur = _get(table, col, *labels)
        if col not in table:
            return "pending", None, ""
        if cur is None:
            return None
        prev = _get(table, _column(kind, label, 1), *labels)
        if prev is None or prev <= 0:
            return None
        v = round((cur / prev - 1) * 100, 2)
        status = "kept" if v >= lo else "partly" if v >= 0.8 * lo else "missed"
        basis = f"YoY {name.lower()} growth from screener {kind} table"
        verb = f"grew {v:.1f}%" if v >= 0 else f"fell {-v:.1f}%"
        why = f"{name} {verb} YoY in {label} against a target of at least {_fmt(lo)}%"
    act = Actual(value=v, unit="%", period=label, basis=basis)
    return status, act, why


def compute_status(p: Promise, quarters: dict, annual: dict) -> tuple[Status, Actual | None] | None:
    """Grade by arithmetic. None means this promise cannot be computed (judge it instead);
    ("pending", None) means the period's actuals are not out yet."""
    out = _grade(p, quarters, annual)
    return None if out is None else (out[0], out[1])


def _computed_row(p: Promise, quarters: dict, annual: dict) -> LedgerRow | None:
    out = _grade(p, quarters, annual)
    if out is None:
        return None
    status, actual, why = out
    if actual is None:
        hz = parse_horizon(p.horizon, p.made_in)
        why = f"Actuals for {hz[1] if hz else 'the period'} are not published yet"
    return LedgerRow(promise=p, status=status, method="computed", actual=actual, rationale=why)


SYSTEM = """You grade whether company management kept promises made on an earlier earnings call, \
using only LATER calls. Search all of the later calls; management often revisits a target \
with new numbers or a new date. Prefer the most recent mention.
Statuses: kept = later evidence shows the promise was achieved or delivered, by its stated \
time if it had one. partly = later evidence shows partial delivery. missed = later evidence \
shows it was not achieved, was cut or lowered, or slipped past its stated time. \
dropped = management stopped mentioning it in the later calls. \
pending = not yet due, or no later evidence of the outcome.
The evidence must concern the same metric and the same period as the promise; a number for a \
different quarter or year is not evidence for this promise.
Restating, reaffirming or repeating the same target is NOT evidence of delivery: use pending. \
The evidence quote must show the outcome, not the promise being repeated.
Rules: evidence_quote must be copied exactly, word for word, from the evidence block, at least \
6 words, from one later source. Give that source's id as evidence_source and the page number from \
its [[pN]] marker as evidence_page. Without a verbatim quote use pending (or dropped). \
rationale is one plain sentence of at most 30 words.
Reply JSON only: {"judgements": [{"id", "status", "evidence_quote", "evidence_source", \
"evidence_page", "rationale"}]} with one entry per promise id."""


def _user_prompt(promises: list[Promise], later: list[Source]) -> str:
    lines = ["PROMISES:"]
    for p in promises:
        lines.append(
            f"- id={p.id} | topic={p.topic} | horizon={p.horizon or 'unspecified'} | "
            f'quote: "{p.citation.quote}"'
        )
    cap = min(90_000, JUDGE_EVIDENCE_CHARS // max(len(later), 1))
    blocks = [f"=== {s.id}: {s.title} ===\n{tagged_text(s, cap)}" for s in later]
    return "\n".join(lines) + "\n\nEVIDENCE (later calls, oldest first):\n\n" + "\n\n".join(blocks)


def _truncate(text: str, n: int = 30) -> str:
    words = text.split()
    return text.strip() if len(words) <= n else " ".join(words[:n]) + "…"


def _judge_one(raw: object, later: list[Source]) -> tuple[Status, Citation | None, str]:
    if not isinstance(raw, dict):
        return "pending", None, _NOT_ASSESSED
    status = raw.get("status")
    if status not in STATUSES:
        status = "pending"
    rationale = raw.get("rationale")
    rationale = _truncate(rationale) if isinstance(rationale, str) and rationale.strip() else ""
    quote, src_id, page = (
        raw.get("evidence_quote"),
        raw.get("evidence_source"),
        raw.get("evidence_page"),
    )
    evidence = None
    if isinstance(quote, str) and quote.strip():
        src = next((s for s in later if s.id == src_id), None)
        hint = page if isinstance(page, int) and not isinstance(page, bool) else None
        evidence = locate(quote, src, hint) if src else None
        if evidence is None:
            return "pending", None, _NO_EVIDENCE
    if status in ("kept", "partly", "missed") and evidence is None:
        return "pending", None, _NO_EVIDENCE
    if status == "dropped" and (evidence is not None or len(later) < 2):
        status = "pending"
    if status == "pending":
        evidence = None
    return status, evidence, rationale or _NOT_ASSESSED  # type: ignore[return-value]


def _judge_group(
    router, promises: list[Promise], later: list[Source]
) -> dict[str, tuple[Status, Citation | None, str]]:
    try:
        reply = router.complete_json("reason", SYSTEM, _user_prompt(promises, later))
    except LLMError:
        return {}
    items = reply.get("judgements") if isinstance(reply, dict) else None
    out: dict[str, tuple[Status, Citation | None, str]] = {}
    ids = {p.id for p in promises}
    for raw in items if isinstance(items, list) else []:
        if isinstance(raw, dict) and raw.get("id") in ids:
            p = next(p for p in promises if p.id == raw["id"])
            out[p.id] = _not_yet_due(p, _judge_one(raw, later), later[-1].quarter)
    return out


def _not_yet_due(p: Promise, verdict: tuple, newest: str | None) -> tuple:
    status = verdict[0]
    if status not in ("kept", "partly"):
        return verdict
    long_term = _LONG.search(normalize(p.citation.quote)) is not None
    hz, nk = parse_horizon(p.horizon, p.made_in), _qkey(newest)
    future = False
    if hz and nk:
        k = _qkey(hz[1]) if hz[0] == "quarter" else (int(hz[1][2:]), 4)
        future = k is not None and k > nk
    return ("pending", None, _NOT_DUE) if long_term or future else verdict


def build_ledger(
    router, promises: list[Promise], sources: list[Source], quarters: dict, annual: dict
) -> Ledger:
    transcripts = [s for s in sources if s.kind == "transcript"]
    by_id = {s.id: s for s in sources}
    rows: list[LedgerRow] = []
    groups: dict[str, list[Promise]] = {}
    for p in promises:
        row = _computed_row(p, quarters, annual)
        if row is not None:
            rows.append(row)
        else:
            groups.setdefault(p.citation.source_id, []).append(p)

    for sid, group in groups.items():
        src = by_id.get(sid)
        key = (_qkey(src.quarter) if src else None) or _qkey(group[0].made_in)
        later = sorted(
            (s for s in transcripts if key and (k := _qkey(s.quarter)) and k > key),
            key=lambda s: _qkey(s.quarter),  # type: ignore[arg-type,return-value]
        )
        if not later:
            rows += [
                LedgerRow(
                    promise=p,
                    status="pending",
                    method="judged",
                    rationale="Too recent to judge",
                )
                for p in group
            ]
            continue
        verdicts = _judge_group(router, group, later)
        for p in group:
            status, ev, why = verdicts.get(p.id, ("pending", None, _NOT_ASSESSED))
            rows.append(
                LedgerRow(promise=p, status=status, method="judged", evidence=ev, rationale=why)
            )

    def order(r: LedgerRow) -> tuple:
        k = _qkey(r.promise.made_in)
        m = re.search(r"-(\d+)$", r.promise.id)
        return (
            k is not None,
            k or (0, 0),
            r.promise.id.rsplit("-", 1)[0],
            int(m.group(1)) if m else 0,
        )

    rows.sort(key=order)
    counts = {s: 0 for s in STATUSES}
    for r in rows:
        counts[r.status] += 1
    resolved = counts["kept"] + counts["partly"] + counts["missed"]
    cred = (counts["kept"] + 0.5 * counts["partly"]) / resolved * 100 if resolved else None
    note = (
        f"Not enough concall transcripts on file (found {len(transcripts)})"
        if len(transcripts) < 2
        else None
    )
    return Ledger(rows=rows, counts=counts, credibility_pct=cred, note=note)
