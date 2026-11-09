"""Extract management guidance from a transcript; keep only quotes verbatim in the source."""

from __future__ import annotations

import logging
import re
import typing

from finn.enrich.grounding import normalize, numbers_grounded
from finn.llm.providers import LLMError
from finn.models import Citation, Promise, Source
from finn.research.cite import locate, sentence_prefix, tagged_text

log = logging.getLogger(__name__)

MAX_PROMISES = 8
METRICS = {
    "revenue_growth",
    "ebitda_margin",
    "pat_growth",
    "capex",
    "order_book",
    "volume_growth",
    "other",
}
UNITS = {"%", "cr", "x", "usd_mn", "usd_bn"}

# Whole words only: "expected", "planned", "targeted", "plant" and "willing" are not cues.
_CUES = re.compile(
    r"\b(?:expect|expects|expecting|will|shall|would|plan to|plans to|planning"
    r"|aim to|aims to|aiming|target|targets|targeting|guide|guidance|guiding"
    r"|intend|intends|intending|anticipate|anticipates|anticipating"
    r"|aspire|aspires|aspiration|commit|committed to|commits"
    r"|outlook|going forward|on track|upcoming|should|likely|confident"
    r"|look to|looking to|look forward|next)\b"
    r"|\bby fy\s*'?\d"
    r"|\b(?:is|are|be|being|remains?|stays?)\s+(?:expected|planned|scheduled|slated|poised"
    r"|set|due|targeted|anticipated|projected|estimated)\s+(?:to|for)\b"
    r"|\b(?:expected|planned|scheduled|slated)\s+(?:to\s+be\s+)?"
    r"(?:commissioned|completed|operational|launched)\b"
)
_CONDITIONAL = re.compile(r"\b(?:if|unless|assuming|provided|subject to)\b")


def _forward_looking(quote: str) -> bool:
    return _CUES.search(normalize(quote)) is not None


def _conditional(cite: Citation, source: Source) -> bool:
    """A conditional word in the quote, or earlier in its sentence (a fragment cut after
    "Unless the macro deteriorates further," is still conditional)."""
    return bool(
        _CONDITIONAL.search(normalize(cite.quote))
        or _CONDITIONAL.search(sentence_prefix(cite, source))
    )


SYSTEM = """You extract management guidance from an earnings-call transcript for an investor.
The transcript has page markers like [[p3]].
Return up to 8 forward-looking statements made by management: guidance, targets, plans and
expectations. Prioritise headline guidance on growth, margins, capex, deals or pipeline, and
strategy. Analyst questions are not promises; skip them.
Only forward-looking statements: targets, guidance, plans, expectations, intentions or
commitments about the future. Exclude statements of current or past fact (results achieved,
the company's current size or margins), even if they contain numbers.
Exclude conditional or hypothetical statements (if, unless, assuming, provided, subject to).
For each item give:
- quote: one complete sentence copied EXACTLY from the transcript, character for character.
  Never paraphrase or stitch sentences together.
- page: the number from the [[pN]] marker of the page the quote is on.
- topic: a short label, e.g. "revenue growth", "deal wins", "margin".
- kind: "quantitative" if the quote states a number, else "qualitative".
- metric: one of revenue_growth, ebitda_margin, pat_growth, capex, order_book, volume_growth,
  other; null if not quantitative.
- target_low, target_high: numbers exactly as stated in the quote, else null.
- unit: one of "%", "cr", "x", "usd_mn", "usd_bn"; null if no target.
- horizon: the period as said ("Q3 FY27", "FY27", "next year"), else null.
Reply as JSON: {"promises": [...]}. If there are none, {"promises": []}."""


def _num(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _opt_str(v: object) -> str | None:
    return v.strip() or None if isinstance(v, str) else None


def extract_promises(
    router, source: Source, guard: dict | None = None, notes: list[str] | None = None
) -> list[Promise]:
    """Grounded promises from one transcript. A model failure (LLMError or a reply of the
    wrong shape) returns [] and adds a plain-English line to `notes`."""
    user = f"Transcript: {source.title} ({source.quarter or 'quarter unknown'})\n\n" + tagged_text(
        source
    )
    unread = f"Guidance from {source.title} could not be read (model unavailable)"
    try:
        reply = router.complete_json("extract_transcript", SYSTEM, user)
    except LLMError as e:
        log.warning("guidance extraction failed for %s: %s", source.id, e)
        if notes is not None:
            notes.append(unread)
        return []
    if not isinstance(reply, dict) or not isinstance(reply.get("promises"), list):
        log.warning("guidance extraction for %s returned an unusable reply", source.id)
        if notes is not None:
            notes.append(unread)
        return []

    if guard is not None:
        guard["promises_proposed"] = guard.get("promises_proposed", 0) + len(reply["promises"])
    out: list[Promise] = []
    seen: set[str] = set()
    for item in reply["promises"]:
        if not isinstance(item, dict):
            continue
        quote = item.get("quote")
        topic = item.get("topic")
        if not isinstance(quote, str) or not isinstance(topic, str) or not topic.strip():
            continue
        hint = item.get("page")
        hint = hint if isinstance(hint, int) and not isinstance(hint, bool) else None
        cite = locate(quote, source, hint)
        if cite is None:
            continue
        if not _forward_looking(cite.quote) or _conditional(cite, source):
            continue
        key = normalize(cite.quote)
        if key in seen:
            continue

        low, high = _num(item.get("target_low")), _num(item.get("target_high"))
        unit = item.get("unit") if item.get("unit") in UNITS else None
        metric = item.get("metric") if item.get("metric") in METRICS else None
        targets = [v for v in (low, high) if v is not None]
        if any(not numbers_grounded(f"{v:g}", cite.quote) for v in targets):
            low = high = unit = None
        targets = [v for v in (low, high) if v is not None]
        kind = "quantitative" if targets else "qualitative"  # kind follows the grounded targets
        if not targets:
            unit = None
        seen.add(key)
        out.append(
            Promise(
                id=f"{source.id}-{len(out) + 1}",
                citation=cite,
                topic=topic.strip(),
                kind=typing.cast(typing.Literal["quantitative", "qualitative"], kind),
                metric=metric,
                target_low=low,
                target_high=high,
                unit=unit,
                horizon=_opt_str(item.get("horizon")),
                made_in=source.quarter or "",
            )
        )
        if len(out) >= MAX_PROMISES:
            break
    if guard is not None:
        guard["promises_kept"] = guard.get("promises_kept", 0) + len(out)
    return out
