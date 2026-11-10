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
from finn.research.ledger import (
    _MISMATCH,
    _REL_YEAR,
    _SEGMENT,
    _horizon_in_quote,
    _horizon_text,
    _long_horizon,
    _qkey,
    parse_horizon,
)

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
    "ebitda_margin": ("EBITDA margin", re.compile(r"\bebitda margins?\b")),
}
_CARD_KEY = {"Revenue": "revenue", "PAT": "pat", "EBITDA margin": "ebitda_margin"}


def _fy(label: str) -> str | None:
    k = _qkey(label)
    return f"FY{k[0]:02d}" if k else None


_THIS_QUARTER = {"this quarter", "current quarter", "the current quarter"}


def _resolve(p: Promise) -> tuple[str, str] | None:
    """The promise's period as ("fy", "FY27") or ("quarter", "Q2 FY27"), or None. A Q4 call's
    "this year"/"next year" stays unresolved: the new fiscal year has begun by then, so either
    phrase may mean it (the ledger's own computed grade refuses them for the same reason)."""
    low = _horizon_text(p.horizon)
    k = _qkey(p.made_in)
    if k and k[1] == 4 and low in _REL_YEAR:
        return None
    if k and low in _THIS_QUARTER:
        return "quarter", f"Q{k[1]} FY{k[0]:02d}"
    return parse_horizon(p.horizon, p.made_in)


def _covers(p: Promise, card: ResultsCard) -> bool:
    """The promise's period is the card's fiscal year or quarter."""
    hz = _resolve(p)
    if hz is None:
        return False
    kind, label = hz
    return label == card.period_label if kind == "quarter" else label == _fy(card.period_label)


def horizon_label(p: Promise, card: ResultsCard) -> str | None:
    """The period as a reader of this card needs it: a label, "was due …" when it has passed,
    or the call's own phrase tied to that call ("next year" means nothing months later)."""
    if not p.horizon:
        return None
    hz = _resolve(p)
    if hz is None:
        return f'"{p.horizon.strip()}", said on the {p.made_in} call'
    kind, label = hz
    card_k = _qkey(card.period_label)
    if kind == "quarter":
        lk = _qkey(label)
        passed = bool(lk and card_k and lk < card_k)
    else:
        fy, cfy = _qkey(f"Q4 {label}"), card_k
        passed = bool(fy and cfy and fy[0] < cfy[0])
    return f"was due {label}" if passed else label


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


_COMPARATIVE = r"(?:lower|higher|less|more|increase|decrease|reduction|savings|cut|down|up)\b"


def _comparative(nums: list[float], quote: str) -> bool:
    """A number followed directly (after its unit) by "lower"/"higher"/… is a change, not the
    level aimed at ("INR600 crores lower than this INR 2,400"). Only the number's own words
    count: in "Rs 20,000 crores of which more than 60%", the "more" belongs to the 60%."""
    text = re.sub(r"(?<=\d),(?=\d)", "", quote)
    for v in nums:
        num = re.escape(f"{v:g}")
        if re.search(num + r"(?![\d.])\s*(?:%|per ?cent|crores?|cr|x)?\s+" + _COMPARATIVE, text):
            return True
    return False


_TARGET_KIND = {
    "revenue_growth": "target",
    "ebitda_margin": "target",
    "pat_growth": "target",
    "order_book": "target",
    "volume_growth": "target",
    "capex": "guided",
}


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
    if _comparative(nums, quote):
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


# Measures that share a word with a results line but are not it. A pace note never fires
# when the quote names one: one quarter beside the wrong measure misleads more than silence.
_PACE_BLOCK = re.compile(
    r"\bvolumes?\b|same[- ]store|like[- ]for[- ]like|\bsssg\b|\blfl\b|per (?:available )?seat"
    r"|unit revenue|realis|per (?:unit|ton|tonne)|\bprask\b|\brask\b|\byields?\b"
    r"|\baum\b|loan book|advances|disburs|\bbook\b|export|domestic|international"
    r"|india business|us business|north america|europe|organic|excluding|\bex-|inorganic"
    r"|embedded|pre-?sales|bookings|collections|adjusted|normali[sz]ed"
    r"|\bh[12]\b|first half|second half|\b9m\b|nine months"
)
_MARGIN = re.compile(r"\bmargins?\b")
_LINE_WORDS = re.compile(
    r"revenues?|sales|top ?line|pat|net profit|profit after tax|bottom ?line|ebitda"
)
NEAR_TOKENS = 8


def _near(line_rx: re.Pattern[str], lo: float, quote: str) -> bool:
    """The target number sits within NEAR_TOKENS words of the line's own word."""
    text = re.sub(r"(?<=\d),(?=\d)", "", quote)
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", text)
    num = f"{lo:g}"
    at_num = [i for i, t in enumerate(tokens) if t == num]
    at_line = [i for i, t in enumerate(tokens) if line_rx.fullmatch(t)]
    return any(abs(i - j) <= NEAR_TOKENS for i in at_num for j in at_line)


def pace_note(p: Promise, card: ResultsCard) -> PaceNote | None:
    """This quarter's filed figure beside the target, or None unless every gate holds."""
    if p.unit != "%" or p.target_low is None or p.metric not in _LINES:
        return None
    if _target(p) is None:  # the stated target must be in the quote, with its unit
        return None
    line, names = _LINES[p.metric]
    quote = normalize(p.citation.quote)
    if not names.search(quote) or _MISMATCH.search(quote) or _SEGMENT.search(quote):
        return None
    if _PACE_BLOCK.search(quote) or re.search(r"\bebit\b", quote):
        return None
    if line != "EBITDA margin" and _MARGIN.search(quote):  # a PAT margin is not PAT growth
        return None
    if not _near(_LINE_WORDS, p.target_low, quote):
        return None
    hz = _resolve(p)
    if hz is None or not _covers(p, card) or not _horizon_in_quote(p.horizon, hz, quote):
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
    if hi is None or hi == lo:
        if _open_ended(lo, quote):
            word = "at or above" if actual >= lo else "below"
        else:
            word = "at" if abs(actual - lo) < 0.05 else "above" if actual > lo else "below"
    elif actual > hi:
        word = "above"
    elif actual >= lo:
        word = "within"
    else:
        word = "below"
    return PaceNote(
        line=line,
        actual=actual,
        basis=basis,
        target_low=lo,
        target_high=hi if hi != lo else None,
        word=word,
        scope="quarter" if hz[0] == "quarter" else "year",
    )


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
    card_k = _qkey(card.period_label)
    long = _long_horizon(text, card_k[0] if card_k else None)
    return (
        long,  # long-horizon promises last
        not _covers(p, card),  # this year's (or this quarter's) first
        p.kind != "quantitative",  # then numbers before words
        (-k[0], -k[1]),  # then the newest call
    )


def _note(r: LedgerRow, d: Dossier, card: ResultsCard) -> PromiseNote:
    p = r.promise
    return PromiseNote(
        topic=p.topic,
        quote=p.citation.quote,
        citation=p.citation,
        call=_call(r, d),
        made_in=p.made_in,
        horizon=p.horizon,
        horizon_label=horizon_label(p, card),
        target=_target(p),
        target_kind=_TARGET_KIND.get(p.metric or "", "figure"),
        pace=pace_note(p, card),
    )


def promise_notes(d: Dossier, card: ResultsCard, limit: int = MAX_NOTES) -> list[PromiseNote]:
    """The company's open promises that matter for this card, best first."""
    if d.ledger is None:
        return []
    open_rows = [r for r in d.ledger.rows if r.status == "pending"]
    open_rows.sort(key=lambda r: _rank(r, card))
    # The same guidance repeated on one call, or on two, is one note; keep the copy that
    # carries a pace sentence, in the place of the first.
    notes: list[PromiseNote] = []
    where: dict[tuple, int] = {}
    for r in open_rows:
        p = r.promise
        note = _note(r, d, card)
        key = (p.metric, p.target_low, p.target_high, p.unit, (p.horizon or "").lower())
        if p.target_low is not None and key in where:
            i = where[key]
            if notes[i].pace is None and note.pace is not None:
                notes[i] = note
            continue
        where[key] = len(notes)
        notes.append(note)
    return notes[:limit]


def attach_promises(conn: sqlite3.Connection, stories: list[Story]) -> None:
    """Give each results story with a card its company's open promises (one lookup a symbol)."""
    cache: dict[str, Dossier | None] = {}
    for st in stories:
        if st.category != "results" or st.results is None:
            continue
        if st.symbol not in cache:
            try:
                cache[st.symbol] = db.get_dossier(conn, st.symbol)
            except (ValidationError, ValueError, sqlite3.DatabaseError) as e:  # incl. bad JSON
                log.warning(
                    "no promises for %s: unreadable dossier: %s", st.symbol, type(e).__name__
                )
                cache[st.symbol] = None
        d = cache[st.symbol]
        if d is not None:
            st.promises = promise_notes(d, st.results)
