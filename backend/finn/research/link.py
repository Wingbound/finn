"""Push meets Pull: a results card beside the promises on the company's own calls.

A quarter never grades a promise; the ledger does that, only on later-call evidence. Here a
results story gets the company's *open* promises, quoted, and, only when every gate holds,
a pace note that puts this quarter's filed number next to the target.
"""

from __future__ import annotations

import logging
import re
import sqlite3

from pydantic import ValidationError

from finn import db
from finn.enrich.grounding import normalize, numbers_grounded
from finn.models import Dossier, LedgerRow, PaceNote, Promise, PromiseNote, ResultsCard, Story
from finn.research.ledger import _LONG_WORDS, _MISMATCH, _SEGMENT, _qkey, parse_horizon

log = logging.getLogger(__name__)

MAX_NOTES = 3

# The quote itself must name the results line; the extractor's `metric` label alone is not
# enough (it calls AUM growth and PRASK "revenue_growth").
_LINES: dict[str, tuple[str, re.Pattern[str]]] = {
    "revenue_growth": (
        "Revenue",
        re.compile(
            r"\b(?:revenue|revenues|sales|top ?line)\b.*\bgrow|\bgrow\w*\b.*\b(?:revenue|revenues|sales|top ?line)\b"
        ),
    ),
    "pat_growth": ("PAT", re.compile(r"\b(?:pat|net profit|profit after tax|bottom ?line)\b")),
    "ebitda_margin": ("EBITDA margin", re.compile(r"\b(?:ebitda|operating) margins?\b")),
}
_CARD_KEY = {"Revenue": "revenue", "PAT": "pat", "EBITDA margin": "ebitda_margin"}


def _fy(label: str) -> str | None:
    k = _qkey(label)
    return f"FY{k[0]:02d}" if k else None


def _covers(p: Promise, card: ResultsCard) -> bool:
    """The promise's horizon is the card's fiscal year or quarter."""
    hz = parse_horizon(p.horizon, p.made_in)
    if hz is None:
        return False
    kind, label = hz
    return label == card.period_label if kind == "quarter" else label == _fy(card.period_label)


# The unit a target is labelled with must be written in the quote too ("18 months" is not
# "18x"), and an open target reads "at least" only when the quote says so.
_UNIT_IN_QUOTE = {
    "%": re.compile(r"%|\bper ?cent\b"),
    "cr": re.compile(r"\bcr(?:ore)?s?\b"),
    "x": re.compile(r"\d\s*(?:x|×)(?![a-z])|\btimes\b"),
    "usd_mn": re.compile(r"\$|\busd\b|\bdollars?\b"),
    "usd_bn": re.compile(r"\$|\busd\b|\bdollars?\b"),
}
_OPEN_BEFORE = (
    r"(?:at least|more than|over|above|in excess of|upwards of)\s+(?:about\s+|around\s+)?"
    r"(?:rs\.?\s*|inr\s*|₹\s*|usd\s*|\$\s*)?"
)
_OPEN_AFTER = r"\s*(?:%|per ?cent|crores?|cr|x|×)?\s*(?:plus\b|\+)"


def _open_ended(lo: float, quote: str) -> bool:
    """'at least' / 'more than' / 'plus' attached to the target's own number."""
    text = re.sub(r"(?<=\d),(?=\d)", "", quote)  # 20,000 -> 20000
    num = re.escape(f"{lo:g}")
    return bool(
        re.search(_OPEN_BEFORE + num + r"(?![\d.])", text) or re.search(num + _OPEN_AFTER, text)
    )


def _inr(v: float) -> str:
    """Indian digit grouping for crore figures: 20000 -> 20,000; 123456 -> 1,23,456."""
    whole, _, frac = f"{v:g}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    while len(head) > 2:
        tail = f"{head[-2:]},{tail}"
        head = head[:-2]
    out = f"{head},{tail}" if head else tail
    return f"{out}.{frac}" if frac else out


def _target(p: Promise) -> str | None:
    """The target as a short label, only when its unit and numbers are in the quote: the
    extractor sometimes merges two figures ("180-odd apps and 600-odd agents"), carries a
    number from elsewhere, or reads "18 months" as 18x, and a label beside a quote must not
    contradict it."""
    if p.target_low is None or p.unit not in _UNIT_IN_QUOTE:
        return None
    quote = normalize(p.citation.quote)
    nums = [p.target_low] + ([p.target_high] if p.target_high is not None else [])
    if not numbers_grounded(" ".join(f"{v:g}" for v in nums), p.citation.quote):
        return None
    if not _UNIT_IN_QUOTE[p.unit].search(quote):
        return None

    def n(v: float) -> str:
        return str(int(v)) if float(v).is_integer() else f"{v:g}"

    lo = n(p.target_low)
    ranged = p.target_high is not None and p.target_high != p.target_low
    rng = f"{lo}–{n(p.target_high)}" if ranged else lo
    if p.unit == "cr":
        hi_txt = f"–{_inr(p.target_high)}" if ranged and p.target_high is not None else ""
        label = f"₹{_inr(p.target_low)}{hi_txt} cr"
    elif p.unit in ("usd_mn", "usd_bn"):
        label = f"${rng} {'mn' if p.unit == 'usd_mn' else 'bn'}"
    else:
        label = f"{rng}{'%' if p.unit == '%' else '×'}"
    open_ended = p.target_high is None and _open_ended(p.target_low, quote)
    return f"at least {label}" if open_ended else label


def pace_note(p: Promise, card: ResultsCard) -> PaceNote | None:
    """This quarter's filed figure beside the target, or None unless every gate holds."""
    if p.unit != "%" or p.target_low is None or p.metric not in _LINES:
        return None
    line, names = _LINES[p.metric]
    quote = normalize(p.citation.quote)
    if not names.search(quote) or _MISMATCH.search(quote) or _SEGMENT.search(quote):
        return None
    if line == "EBITDA margin" and re.search(r"\bebit\b", quote):
        return None
    if not _covers(p, card):
        return None
    key = _CARD_KEY[line]
    if line == "EBITDA margin":
        row = next((m for m in card.margins if m.key == key), None)
        actual = row.value_pct if row else None
        basis = f"margin in {card.period_label}"
    else:
        row = next((m for m in card.metrics if m.key == key), None)
        actual = row.yoy_pct if row else None
        basis = f"YoY growth in {card.period_label}"
    if actual is None:
        return None
    lo, hi = p.target_low, p.target_high
    if hi is None:
        word = "at or above" if actual >= lo else "below"
    elif actual > hi:
        word = "above"
    elif actual >= lo:
        word = "within"
    else:
        word = "below"
    return PaceNote(line=line, actual=actual, basis=basis, target_low=lo, target_high=hi, word=word)


def _call(row: LedgerRow, d: Dossier) -> str:
    src = next((s for s in d.sources if s.id == row.promise.citation.source_id), None)
    name = (
        f"{src.quarter} call"
        if src and src.quarter
        else (src.title if src else row.promise.made_in)
    )
    return f"{name}, p. {row.promise.citation.page}"


def _rank(row: LedgerRow, card: ResultsCard) -> tuple:
    p = row.promise
    text = normalize(f"{p.horizon or ''} {p.citation.quote}")
    k = _qkey(p.made_in) or (0, 0)
    long = bool(_LONG_WORDS.search(text))
    return (
        long,  # long-horizon promises last
        not _covers(p, card),  # this year's (or this quarter's) first
        p.kind != "quantitative",  # then numbers before words
        (-k[0], -k[1]),  # then the newest call
    )


def promise_notes(d: Dossier, card: ResultsCard, limit: int = MAX_NOTES) -> list[PromiseNote]:
    """The company's open promises that matter for this card, best first."""
    if d.ledger is None:
        return []
    open_rows = [r for r in d.ledger.rows if r.status == "pending"]
    open_rows.sort(key=lambda r: _rank(r, card))
    # The same guidance repeated on one call, or on two, is one note.
    seen: set[tuple] = set()
    unique: list[LedgerRow] = []
    for r in open_rows:
        p = r.promise
        key = (p.metric, p.target_low, p.target_high, p.unit, (p.horizon or "").lower())
        if p.target_low is not None and key in seen:
            continue
        seen.add(key)
        unique.append(r)
    open_rows = unique
    return [
        PromiseNote(
            topic=r.promise.topic,
            quote=r.promise.citation.quote,
            citation=r.promise.citation,
            call=_call(r, d),
            made_in=r.promise.made_in,
            horizon=r.promise.horizon,
            target=_target(r.promise),
            pace=pace_note(r.promise, card),
        )
        for r in open_rows[:limit]
    ]


def attach_promises(conn: sqlite3.Connection, stories: list[Story]) -> None:
    """Give each results story with a card its company's open promises (one lookup a symbol)."""
    cache: dict[str, Dossier | None] = {}
    for st in stories:
        if st.category != "results" or st.results is None:
            continue
        if st.symbol not in cache:
            try:
                cache[st.symbol] = db.get_dossier(conn, st.symbol)
            except (ValidationError, ValueError, sqlite3.DatabaseError) as e:
                log.warning(
                    "no promises for %s: unreadable dossier: %s", st.symbol, type(e).__name__
                )
                cache[st.symbol] = None
        d = cache[st.symbol]
        if d is not None:
            st.promises = promise_notes(d, st.results)
