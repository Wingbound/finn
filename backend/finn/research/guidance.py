"""Extract management guidance from a transcript; keep only quotes verbatim in the source."""

from __future__ import annotations

import logging
import re
import typing

from finn.enrich.grounding import normalize, numbers_grounded
from finn.llm.providers import LLMError
from finn.models import Promise, Source
from finn.research.cite import locate, tagged_text

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

_CUES = re.compile(
    r"\b(?:expect|will|shall|would|target|guid|aim|plan|intend|aspir|anticipat|commit"
    r"|endeavou?r)|\b(?:outlook|going forward|on track|by fy|next|upcoming|should|likely"
    r"|confident|look to|looking to|look forward)\b"
)


def _forward_looking(quote: str) -> bool:
    return _CUES.search(normalize(quote)) is not None


SYSTEM = """You extract management guidance from an earnings-call transcript for an investor.
The transcript has page markers like [[p3]].
Return up to 8 forward-looking statements made by management: guidance, targets, plans and
expectations. Prioritise headline guidance on growth, margins, capex, deals or pipeline, and
strategy. Analyst questions are not promises; skip them.
Only forward-looking statements: targets, guidance, plans, expectations, intentions or
commitments about the future. Exclude statements of current or past fact (results achieved,
the company's current size or margins), even if they contain numbers.
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


def extract_promises(router, source: Source, guard: dict | None = None) -> list[Promise]:
    user = f"Transcript: {source.title} ({source.quarter or 'quarter unknown'})\n\n" + tagged_text(
        source
    )
    try:
        reply = router.complete_json("extract_transcript", SYSTEM, user)
    except LLMError as e:
        log.warning("guidance extraction failed for %s: %s", source.id, e)
        return []
    if not isinstance(reply, dict) or not isinstance(reply.get("promises"), list):
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
        if not _forward_looking(cite.quote):
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
