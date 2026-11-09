"""One-line 'why it matters' briefs for material stories, guarded by number grounding."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime

from pydantic import ValidationError

from finn import db
from finn.classify.materiality import score_filing
from finn.enrich import EnrichResult
from finn.enrich.grounding import (
    MIN_SENTENCE_WORDS,
    normalize,
    numbers_grounded,
    phrase_in_text,
    split_sentences,
)
from finn.enrich.pdftext import get_doc_text, relevant_window
from finn.ingest.nse import NSEUnavailable
from finn.llm.providers import LLMError
from finn.models import Brief, Fact, Filing, Story

log = logging.getLogger(__name__)

KIND = "brief"
BRIEF_CATEGORIES = {
    "mna",
    "fund_raise",
    "credit_rating",
    "litigation",
    "pledging",
    "capex",
    "insider_trading",
}
MIN_SCORE = 45
MAX_ONE_LINER_WORDS = 30
MAX_FALLBACK_WORDS = 40
MAX_FACTS = 3
WINDOW_CHARS = 6000

CATEGORY_TERMS: dict[str, list[str]] = {
    "mna": [
        "acquisition",
        "merger",
        "amalgamation",
        "stake",
        "consideration",
        "share purchase",
        "scheme",
    ],
    "credit_rating": [
        "rating",
        "CRISIL",
        "ICRA",
        "CARE",
        "India Ratings",
        "outlook",
        "upgrade",
        "downgrade",
        "reaffirm",
    ],
    "litigation": ["court", "tribunal", "order", "penalty", "notice", "SEBI", "show cause"],
    "fund_raise": ["allot", "issue", "QIP", "preferential", "debenture", "warrant"],
    "pledging": ["pledge", "encumbrance", "release"],
    "capex": ["capacity", "plant", "capex", "expansion", "investment"],
    "insider_trading": ["acquisition", "disposal", "shares", "promoter"],
}

SYSTEM_PROMPT = """You write one-line briefs about Indian stock-exchange filings for investors.

Reply with JSON only: {"one_liner": str, "facts": [{"label": str, "value": str}], "quote": str|null}

- one_liner: ONE plain-English sentence, at most 30 words, on why an investor should care.
- Use ONLY numbers that appear in the source text. Never compute, round or convert numbers.
- facts: up to 3 key facts (amounts, percentages, dates, counterparties). Each value must be \
copied from the source text.
- quote: one short supporting sentence or phrase copied verbatim from the source, else null.

If unsure, leave a field out rather than guess."""


def _fallback(f: Filing) -> Brief | None:
    """NSE's own summary, first sentence, at most 40 words."""
    sentences = split_sentences(f.nse_summary or "")
    if not sentences or not sentences[0].strip():
        return None
    words = sentences[0].split()
    line = " ".join(words)
    if len(words) > MAX_FALLBACK_WORDS:
        line = " ".join(words[:MAX_FALLBACK_WORDS]) + "…"
    return Brief(one_liner=line, by="nse_summary", source_seq_id=f.seq_id)


# Unit words a numeric fact may carry even when the source spells the unit differently.
UNIT_WORDS = frozenset({
    "crore", "crores", "cr", "lakh", "lakhs", "rs", "inr", "mn", "million", "bn", "billion",
    "per", "cent", "percent", "shares", "equity", "each", "face", "value",
})  # fmt: skip
_WORD = re.compile(r"\w+")


def _fact_words_grounded(value: str, source: str) -> bool:
    """Every alphabetic word of 3+ letters in value, bar unit words, is a word in source."""
    words = [w for w in _WORD.findall(normalize(value)) if w.isalpha() and len(w) >= 3]
    return all(phrase_in_text(w, source) for w in words if w not in UNIT_WORDS)


def _clean_facts(raw: object, source: str) -> list[Fact]:
    if not isinstance(raw, list):
        return []
    out: list[Fact] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label, value = item.get("label"), item.get("value")
        if not isinstance(label, str) or not isinstance(value, str):
            continue
        if not label.strip() or not value.strip():
            continue
        if any(ch.isdigit() for ch in value):
            if not numbers_grounded(value, source) or not _fact_words_grounded(value, source):
                continue
        elif len(normalize(value)) < 3 or not phrase_in_text(value, source):
            continue
        out.append(Fact(label=label.strip(), value=value.strip()))
        if len(out) == MAX_FACTS:
            break
    return out


def make_brief(router, f: Filing, text: str, category: str | None = None) -> Brief | None:
    """LLM brief with grounded numbers; NSE summary fallback; None if neither exists.

    LLMError propagates so the caller can retry later instead of saving a fallback.
    """
    terms = CATEGORY_TERMS.get(category or "", [])
    source = f"{f.subject}\n{f.nse_summary or ''}\n{relevant_window(text, terms, WINDOW_CHARS)}"
    reply = router.complete_json("oneliner", SYSTEM_PROMPT, f"SOURCE TEXT:\n{source}")
    one = reply.get("one_liner") if isinstance(reply, dict) else None
    if (
        not isinstance(one, str)
        or not one.strip()
        or len(one.split()) > MAX_ONE_LINER_WORDS
        or not numbers_grounded(one, source)
    ):
        return _fallback(f)
    quote = reply.get("quote")
    if (
        not isinstance(quote, str)
        or not quote.strip()
        or not phrase_in_text(quote, source, MIN_SENTENCE_WORDS)
    ):
        quote = None
    return Brief(
        one_liner=one.strip(),
        facts=_clean_facts(reply.get("facts"), source),
        quote=quote.strip() if quote else None,
        by="llm",
        source_seq_id=f.seq_id,
    )


def enrich_briefs(
    conn: sqlite3.Connection, client, router, since: datetime, subscribed: set[str]
) -> EnrichResult:
    """Write briefs for material filings since `since` that have none saved yet.

    LLM and NSE failures are reported in `failed` and nothing is saved (retried next refresh).
    """
    res = EnrichResult()
    for f, cls in db.filings_missing_enrichment(conn, KIND, BRIEF_CATEGORIES, since):
        if cls.noise or score_filing(f, cls, subscribed).score < MIN_SCORE:
            continue
        try:
            text = get_doc_text(conn, client, f.pdf_url) if f.pdf_url else ""
            text = text if text.strip() else (f.nse_summary or "")
            if not text.strip():
                db.save_enrichment(conn, f.seq_id, KIND, {"brief": None, "reason": "no text"}, None)
                res.empty += 1
                continue
            brief = make_brief(router, f, text, cls.category)
        except (LLMError, NSEUnavailable) as e:
            log.warning("brief enrichment failed for %s: %s", f.seq_id, e)
            res.failed[f.seq_id] = str(e)
            continue
        except Exception as e:  # one bad filing must not stop the batch
            log.exception("brief enrichment crashed for %s", f.seq_id)
            res.failed[f.seq_id] = f"{type(e).__name__}: {e}"
            continue
        if brief is None:
            db.save_enrichment(
                conn, f.seq_id, KIND, {"brief": None, "reason": "no valid brief"}, router.last_model
            )
            res.empty += 1
            continue
        db.save_enrichment(
            conn, f.seq_id, KIND, {"brief": brief.model_dump(mode="json")}, router.last_model
        )
        res.done += 1
    return res


def attach_briefs(conn: sqlite3.Connection, stories: list[Story]) -> None:
    """Give each story the brief of its headline filing, else its first member with one."""
    targets = [st for st in stories if st.category in BRIEF_CATEGORIES]
    ids = [m.filing.seq_id for st in targets for m in st.members]
    saved = db.get_enrichments(conn, ids, KIND)
    for st in targets:
        for m in [st.headline, *st.members]:
            raw = (saved.get(m.filing.seq_id) or {}).get("brief")
            if not raw:
                continue
            try:
                st.brief = Brief.model_validate(raw)
            except ValidationError:  # a corrupt stored row must not break the digest
                log.warning("skipping corrupt brief row for %s", m.filing.seq_id)
                continue
            break
