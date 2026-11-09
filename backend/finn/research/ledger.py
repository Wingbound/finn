"""Promise Ledger: grade each past promise, by code where numbers allow, else by evidence."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Literal

from finn.enrich.grounding import normalize, numbers_grounded
from finn.llm.providers import LLMError
from finn.models import Actual, Citation, Ledger, LedgerRow, Promise, Source, Status
from finn.research.cite import locate, tag_pages
from finn.research.financials import is_lender, year_end_month

log = logging.getLogger(__name__)

STATUSES = ("kept", "partly", "missed", "pending", "dropped")
_COMPUTED = {"revenue_growth", "ebitda_margin", "pat_growth"}
_QTR = re.compile(r"\bQ([1-4])\s*FY\s*(\d{2}|\d{4})\b", re.IGNORECASE)
_FY = re.compile(r"\b(?:FY|fiscal)\s*(\d{2}|\d{4})\b", re.IGNORECASE)
_QMONTH = {1: "Jun", 2: "Sep", 3: "Dec", 4: "Mar"}
_NOT_ASSESSED = "Not assessed"  # the judge never returned a verdict for this promise
_NO_EVIDENCE = "No verifiable later evidence"
_NO_OUTCOME = "No later evidence of the outcome yet"
_DROPPED = "Not mentioned in the later calls"
_SEE_EVIDENCE = "See the later evidence quote."
_JUDGE_FAILED = "Some promises could not be judged (model unavailable)"
MAX_RATIONALE_WORDS = 30
MIN_RESOLVED = 3  # credibility is not shown on fewer resolved promises
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
_REL_YEAR = {
    "this year", "current year", "this fiscal", "this financial year",
    "next year", "next fiscal", "next financial year",
}  # fmt: skip


def _horizon_text(horizon: str | None) -> str:
    low = re.sub(r"\s+", " ", (horizon or "").strip().lower())
    return re.sub(r"^(in|for|during) ", "", low)


def parse_horizon(horizon: str | None, made_in: str) -> Horizon | None:
    """Resolve only when the whole phrase is an explicit label or a known relative phrase."""
    low = _horizon_text(horizon)
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


def _period_key(hz: Horizon) -> tuple[int, int] | None:
    """Comparable (yy, quarter) for a resolved horizon; a fiscal year ends at its Q4."""
    kind, label = hz
    return _qkey(label) if kind == "quarter" else (int(label[2:]), 4)


# C1 gates. A computed grade is the authoritative one, so it is given only when the quote
# itself names the metric and the period, and nothing in it hints at a different measure.
_METRIC_WORDS = {
    "revenue_growth": re.compile(r"\b(?:revenues?|sales|top line|topline|turnover)\b"),
    "pat_growth": re.compile(r"\b(?:pat|net profits?|profit after tax)\b"),
    "ebitda_margin": re.compile(r"\b(?:ebitda|operating margins?|opm)\b"),
}
_MISMATCH = re.compile(
    r"\bebit\b|\bqoq\b|\bquarter[- ]on[- ]quarter\b|\bsequential\w*|\bcqgr\b"
    r"|\bconstant currency\b|\bdollar\w*|\busd\b|\bus\$|\$|\bbps\b|\bbasis points?\b"
    r"|\bexpan\w*|\bimprov\w*|\bby \d"
)
_Q_MENTION = re.compile(r"\bq([1-4])\s*fy\s*'?(\d{4}|\d{2})\b")
_FY_MENTION = re.compile(r"\b(?:fy|fiscal(?: year)?)\s*'?(\d{4}|\d{2})\b")
_PART_OF_YEAR = re.compile(r"\b(?:q[1-4]|h[12]|[1-4]q|9m|quarter|half)\s*(?:of\s+)?(?:the\s+)?$")
_SPAN = re.compile(r"\s*(?:-|–|to)\s*(?:fy\s*)?\d{2}")


def _horizon_in_quote(horizon: str | None, hz: Horizon, quote: str) -> bool:
    """The resolved period, or the relative phrase, is stated in the (normalized) quote.
    FY27, FY 27, FY2027 and fiscal 2027 match each other; Q3 FY27 matches Q3FY27. A fiscal
    year inside a quarter or half label ("Q3 FY27") or a span ("FY27-28") does not count."""
    low = _horizon_text(horizon)
    kind, label = hz
    if not (_H_QTR.fullmatch(low) or _H_FY.fullmatch(low)):
        return re.search(r"(?<!\w)" + re.escape(low) + r"(?!\w)", quote) is not None
    if kind == "quarter":
        return any(
            f"Q{m.group(1)} FY{_yy(m.group(2)):02d}" == label for m in _Q_MENTION.finditer(quote)
        )
    for m in _FY_MENTION.finditer(quote):
        if f"FY{_yy(m.group(1)):02d}" != label:
            continue
        if _PART_OF_YEAR.search(quote[: m.start()]) or _SPAN.match(quote, m.end()):
            continue
        return True
    return False


def _gated(p: Promise, quote: str, annual: dict) -> Horizon | None:
    """The horizon to compute against, or None when any C1 gate sends the promise to the judge."""
    if year_end_month(annual) != "Mar":
        return None  # quarter and FY columns are mapped for a March fiscal year only
    if p.metric == "ebitda_margin" and is_lender(annual):
        return None
    if not _METRIC_WORDS[p.metric].search(quote) or _MISMATCH.search(quote):  # type: ignore[index]
        return None
    hz = parse_horizon(p.horizon, p.made_in)
    made = _qkey(p.made_in)
    if hz is None or made is None:
        return None
    key = _period_key(hz)
    if key is None or key <= made:
        return None  # the period must end after the call
    if made[1] == 4 and _horizon_text(p.horizon) in _REL_YEAR:
        return None  # "this year" in a Q4 call may mean the year just ended or the new one
    return hz if _horizon_in_quote(p.horizon, hz, quote) else None


def _target(p: Promise) -> str:
    lo, hi = p.target_low, p.target_high
    assert lo is not None
    return f"{_fmt(lo)}–{_fmt(hi)}%" if hi is not None and hi > lo else f"at least {_fmt(lo)}%"


_SEGMENT = re.compile(r"segment|division|vertical|business unit|subsidiary")
_NOT_DUE = "Target not yet due — tracking is not delivery"

# Lenient period scan, used only to downgrade a judged kept/partly to pending (never to grade).
_SCAN = re.compile(
    r"\bq(?P<q>[1-4])\s*fy\s*'?(?P<qy>\d{4}|\d{2})\b"
    r"|\b(?:fy|fiscal(?: year)?)\s*'?(?P<fy>\d{4}|\d{2})\b"
    r"|\b(?:march|mar)\s+(?P<mar>20\d{2})\b"
    r"|\b(?P<rel>this financial year|this fiscal|this year|current financial year|current fiscal"
    r"|current year|next financial year|next fiscal|next year|next quarter|coming quarter)\b"
)
_LONG_WORDS = re.compile(r"long[- ]term|medium[- ]term|aspiration|over the next few years")
# FY labels, or a bare calendar year after a time word ("by 2030"; not "Rs 2075 crore").
_YEARS = re.compile(
    r"\b(?:fy|fiscal(?: year)?)\s*'?(\d{4}|\d{2})\b"
    r"|\b(?:by|in|till|until|through|before|beyond|vision|cy|calendar year|end of)\s+(20\d{2})\b"
)
LONG_YEARS = 2  # a fiscal year this far past the newest call is a long-horizon target


def _scan_period(text: str, made_in: str) -> tuple[int, int] | None:
    """(yy, quarter) of the first period mentioned in normalized text. Year-level mentions
    end at Q4; "march 2027" is FY27. "This year" follows the call: in a Q4 call the new
    fiscal year has begun, so it means the next FY."""
    made = _qkey(made_in)
    for m in _SCAN.finditer(text):
        if m.group("q"):
            return _yy(m.group("qy")), int(m.group("q"))
        if m.group("fy") or m.group("mar"):
            return _yy(m.group("fy") or m.group("mar")), 4
        if made is None:
            continue
        yy, q = made
        rel = m.group("rel")
        if rel in ("next quarter", "coming quarter"):
            return (yy, q + 1) if q < 4 else (yy + 1, 1)
        current = yy + 1 if q == 4 else yy
        return current + (1 if rel.startswith("next") else 0), 4
    return None


def _long_horizon(text: str, newest_fy: int | None) -> bool:
    if _LONG_WORDS.search(text):
        return True
    if newest_fy is None:
        return False
    return any(_yy(a or b) >= newest_fy + LONG_YEARS for a, b in _YEARS.findall(text))


def _grade(p: Promise, quarters: dict, annual: dict) -> tuple[Status, Actual | None, str] | None:
    quote = normalize(p.citation.quote)
    if _SEGMENT.search(quote):
        return None
    if (
        p.kind != "quantitative"
        or p.metric not in _COMPUTED
        or p.unit != "%"
        or p.target_low is None
        or p.target_low <= 0
    ):
        return None
    hz = _gated(p, quote, annual)
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
        why = f"{name} was {v:.1f}% in {label} against a target of {_target(p)}"
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
        why = f"{name} {verb} YoY in {label} against a target of {_target(p)}"
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
shows it was not achieved: missed only if management cut, lowered or moved the target, or the \
stated time passed without it. dropped = management stopped mentioning it in the later calls; \
never use dropped for a call marked TRUNCATED, whose later pages are not shown. \
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
        hz = parse_horizon(p.horizon, p.made_in)
        when = f"made in {p.made_in or 'an unknown quarter'}" + (
            f"; target period {hz[1]}" if hz else ""
        )
        lines.append(
            f"- id={p.id} | topic={p.topic} | horizon={p.horizon or 'unspecified'} ({when}) | "
            f'quote: "{p.citation.quote}"'
        )
    tagged = _evidence(later)
    blocks = [
        f"=== {s.id}: {s.title} ===\n{text}" for s, (text, _) in zip(later, tagged, strict=True)
    ]
    cut = [s.id for s, (_, truncated) in zip(later, tagged, strict=True) if truncated]
    head = "\n\nEVIDENCE (later calls, oldest first):\n\n"
    if cut:
        head += f"TRUNCATED (later pages not shown): {', '.join(cut)}.\n\n"
    return "\n".join(lines) + head + "\n\n".join(blocks)


def _evidence(later: list[Source]) -> list[tuple[str, bool]]:
    """Each later call's tagged pages under the shared evidence budget, and whether cut."""
    cap = min(90_000, JUDGE_EVIDENCE_CHARS // max(len(later), 1))
    return [tag_pages(s, cap) for s in later]


def _rationale(raw: object, p: Promise, evidence: Citation) -> str:
    """The judge's sentence, only if short and every number in it is in the promise or the
    evidence quote; otherwise a pointer to the evidence."""
    if not isinstance(raw, str) or not raw.strip() or len(raw.split()) > MAX_RATIONALE_WORDS:
        return _SEE_EVIDENCE
    if not numbers_grounded(raw, p.citation.quote + "\n" + evidence.quote):
        return _SEE_EVIDENCE
    return raw.strip()


def _judge_one(
    raw: dict, later: list[Source], p: Promise, truncated: bool = False
) -> tuple[Status, Citation | None, str]:
    """Validate one verdict. dropped needs 2+ later calls, none of them truncated."""
    status = raw.get("status")
    if status not in STATUSES:
        status = "pending"
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
    if status in ("kept", "partly", "missed"):
        if evidence is None:
            return "pending", None, _NO_EVIDENCE
        return status, evidence, _rationale(raw.get("rationale"), p, evidence)  # type: ignore[return-value]
    if status == "dropped" and evidence is None and len(later) >= 2 and not truncated:
        return "dropped", None, _DROPPED
    return "pending", None, _NO_OUTCOME


def _judge_group(
    router, promises: list[Promise], later: list[Source], stats: dict | None = None
) -> tuple[dict[str, tuple[Status, Citation | None, str]], bool]:
    """Verdicts by promise id, and whether the model call itself failed."""
    try:
        reply = router.complete_json("reason", SYSTEM, _user_prompt(promises, later))
    except LLMError as e:
        log.warning("ledger judge failed for %s: %s", promises[0].citation.source_id, e)
        return {}, True
    items = reply.get("judgements") if isinstance(reply, dict) else None
    if not isinstance(items, list):
        return {}, True
    out: dict[str, tuple[Status, Citation | None, str]] = {}
    by_id = {p.id: p for p in promises}
    truncated = any(cut for _, cut in _evidence(later))
    for raw in items:
        if isinstance(raw, dict) and (p := by_id.get(raw.get("id"))) is not None:  # type: ignore[arg-type]
            verdict = _judge_one(raw, later, p, truncated)
            verdict = _guard_verdict(p, verdict, stats)
            out[p.id] = _not_yet_due(p, verdict, later[-1].quarter)
    return out, False


_G_QTR = re.compile(r"q([1-4])\s*fy\s*'?(\d{4}|\d{2})")
_G_FY = re.compile(r"(?:fy|fiscal(?: year)?)\s*'?(\d{4}|\d{2})")
_G_QMENTION = re.compile(
    r"q(?P<q>[1-4])(?:\s*fy\s*'?(?P<y>\d{4}|\d{2}))?\b"
    r"|\b(?P<ord>first|second|third|fourth) quarter\b"
    r"|\b(?P<mon>june|september|december|march) quarter\b"
)
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_MON = {"june": 1, "september": 2, "december": 3, "march": 4}
_PERIOD_MSG = "The later quote is about a different period"
_RESTATED_MSG = "The later call restated the target; delivery is not shown yet"
_FUTURE = re.compile(
    r"\b(?:expect|expects|expecting|will|shall|plan to|plans to|planning to|aim to|aims to"
    r"|intend|intends|anticipate|anticipates|on track|going forward|is expected to"
    r"|are expected to|remain committed|should be)\b"
)
_DELIVERED = re.compile(
    r"\b(?:came in|stood at|delivered|achieved|reached|crossed|completed|commissioned"
    r"|commenced|started|launched|received|reported|grew|declined|met|was|were|has been"
    r"|have been|had|did)\b"
)
_LOWER_BETTER = re.compile(
    r"\b(?:below|under|less than|lower than|at most|not exceed|no more than|cap|reduce"
    r"|bring down|within|maximum)\b"
)
_PERIOD_LABEL = re.compile(
    r"\b(?:FY\s*'?\d{2,4}|Q[1-4]|H[12]|9M|[1-4]Q)\b|\b(?:19|20)\d{2}\b", re.IGNORECASE
)
_G_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_G_PCT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:%|percent)")
BELOW_TARGET_RATIO = 0.98


def _other_period(p: Promise, ev: str) -> bool:
    h = normalize(p.horizon or "")
    hq, hf = _G_QTR.search(h), _G_FY.search(h)
    if hq:
        want: tuple[int, int | None] = (int(hq.group(1)), _yy(hq.group(2)))
    elif hf:
        want = (0, _yy(hf.group(1)))
    else:
        return False
    text = normalize(ev)
    mentions: list[tuple[int, int | None]] = []
    for m in _G_QMENTION.finditer(text):
        q = int(m["q"]) if m["q"] else _ORD[m["ord"]] if m["ord"] else _MON[m["mon"]]
        mentions.append((q, _yy(m["y"]) if m["y"] else None))
    if hq:
        return bool(mentions) and not any(
            q == want[0] and y in (None, want[1]) for q, y in mentions
        )
    fys = [_yy(m.group(1)) for m in _G_FY.finditer(_G_QMENTION.sub(" ", text))]
    return bool(fys) and want[1] not in fys


def _restated(ev: str) -> bool:
    text = normalize(ev)
    return bool(_FUTURE.search(text)) and not _DELIVERED.search(text)


def _below_target(p: Promise, ev: str) -> str | None:
    """The rationale when every comparable number in the evidence is below the target."""
    lo = p.target_low
    if p.kind != "quantitative" or lo is None or _LOWER_BETTER.search(normalize(p.citation.quote)):
        return None
    text = _PERIOD_LABEL.sub(" ", normalize(ev))
    if p.unit == "%":
        nums = [float(m.replace(",", "")) for m in _G_PCT.findall(text)]
    else:
        hi = max(lo, p.target_high or lo)
        nums = [float(m.replace(",", "")) for m in _G_NUM.findall(text)]
        nums = [n for n in nums if 0.1 * lo <= n <= 10 * hi]
    if not nums or not all(n < BELOW_TARGET_RATIO * lo for n in nums):
        return None
    hi = p.target_high
    target = f"{_fmt(lo)}–{_fmt(hi)}" if hi is not None and hi > lo else f"at least {_fmt(lo)}"
    return f"The later figure ({_fmt(max(nums))}) is below the {target} target"


def _guard_verdict(p: Promise, verdict: tuple, stats: dict | None) -> tuple:
    """Downgrade a judged verdict to pending when its evidence is about another period
    (kept/partly/missed), restates the target (kept/partly) or is below it (kept)."""
    status, ev = verdict[0], verdict[1]
    if status not in ("kept", "partly", "missed") or ev is None:
        return verdict
    why = reason = None
    if _other_period(p, ev.quote):
        why, reason = _PERIOD_MSG, "other_period"
    elif status != "missed" and _restated(ev.quote):
        why, reason = _RESTATED_MSG, "restated"
    elif status == "kept" and (msg := _below_target(p, ev.quote)):
        why, reason = msg, "below_target"
    if reason is None:
        return verdict
    if stats is not None:
        stats["verdicts_downgraded"][reason] += 1
    return "pending", None, why


def _not_yet_due(p: Promise, verdict: tuple, newest: str | None) -> tuple:
    """A kept/partly verdict becomes pending when the target's period ends after the newest
    later call, or the target is long-horizon. Only ever downgrades."""
    if verdict[0] not in ("kept", "partly"):
        return verdict
    text = normalize(f"{p.horizon or ''}\n{p.citation.quote}")
    nk = _qkey(newest)
    k = _scan_period(text, p.made_in)
    future = k is not None and nk is not None and k > nk
    if future or _long_horizon(text, nk[0] if nk else None):
        return "pending", None, _NOT_DUE
    return verdict


def build_ledger(
    router,
    promises: list[Promise],
    sources: list[Source],
    quarters: dict,
    annual: dict,
    *,
    notes: list[str] | None = None,
    should_stop: Callable[[], bool] | None = None,
    stats: dict | None = None,
) -> Ledger:
    """Grade every promise. Model failures leave rows pending ("Not assessed") and add one
    plain-English line to `notes`. `should_stop` is checked before each judge call; once it
    returns True the remaining groups are left pending."""
    if stats is not None:
        stats.setdefault(
            "verdicts_downgraded", {"other_period": 0, "restated": 0, "below_target": 0}
        )
    judge_failed = stopped = False
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
        stopped = stopped or (should_stop is not None and should_stop())
        if stopped:
            verdicts, failed = {}, False
        else:
            verdicts, failed = _judge_group(router, group, later, stats)
        judge_failed |= failed
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
    if notes is not None:
        if judge_failed:
            notes.append(_JUDGE_FAILED)
        if stopped:
            notes.append("Remaining promise checks skipped: build deadline reached")
    counts = {s: 0 for s in STATUSES}
    for r in rows:
        counts[r.status] += 1
    resolved = counts["kept"] + counts["partly"] + counts["missed"]
    cred = (
        (counts["kept"] + 0.5 * counts["partly"]) / resolved * 100
        if resolved >= MIN_RESOLVED
        else None
    )
    note = (
        f"Not enough concall transcripts on file (found {len(transcripts)})"
        if len(transcripts) < 2
        else None
    )
    return Ledger(rows=rows, counts=counts, credibility_pct=cred, note=note)
