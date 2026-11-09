"""Citation guard: a quote is kept only if it is verbatim in the source."""

from __future__ import annotations

import re

from finn.enrich.grounding import normalize
from finn.models import Citation, Source

MIN_QUOTE_WORDS = 6
_NEGATIONS = {
    "not", "no", "never", "cannot", "can't", "won't", "don't", "doesn't", "didn't",
    "isn't", "aren't", "wasn't", "unlikely", "neither", "nor", "without",
}  # fmt: skip
_SENT_END = re.compile(r"[.!?](?=\s)")
_WORD = re.compile(r"[\w']+")


def _prefixes(q: str, text: str):
    """For each verbatim occurrence of the normalized quote q in text (word boundaries): the
    earlier part of its sentence, normalized."""
    t = normalize(text)
    for m in re.finditer(r"(?<!\w)" + re.escape(q) + r"(?!\w)", t):
        prefix = t[: m.start()]
        ends = list(_SENT_END.finditer(prefix))
        yield prefix[ends[-1].end() :] if ends else prefix


def _clean(prefix: str) -> bool:
    return not _NEGATIONS.intersection(_WORD.findall(prefix))


def _found(quote: str, text: str) -> bool:
    """Quote occurs verbatim (normalized, on word boundaries) with no negation earlier in
    the same sentence, so a fragment cannot flip the meaning of its source sentence."""
    q = normalize(quote)
    if len(q.split()) < MIN_QUOTE_WORDS:
        return False
    return any(_clean(p) for p in _prefixes(q, text))


def sentence_prefix(c: Citation, source: Source) -> str:
    """The earlier part of the quote's sentence at the occurrence `locate` accepts on the
    cited page (or that page joined to the next); "" when the quote starts its sentence."""
    q, pages, i = normalize(c.quote), source.pages, c.page - 1
    if not 0 <= i < len(pages):
        return ""
    texts = [pages[i]] + ([pages[i] + " " + pages[i + 1]] if i + 1 < len(pages) else [])
    for text in texts:
        for p in _prefixes(q, text):
            if _clean(p):
                return p.lstrip()
    return ""


def locate(quote: str, source: Source, hint_page: int | None) -> Citation | None:
    """Find quote verbatim (after normalization) in source. Tries the hint page, then every
    page in order, then adjacent page pairs (a quote straddling a page break, cited to the
    first page of the pair). Returns None if nowhere or under 6 words."""
    q = quote.strip()
    pages = source.pages
    order = list(range(len(pages)))
    if hint_page is not None and 1 <= hint_page <= len(pages):
        order.remove(hint_page - 1)
        order.insert(0, hint_page - 1)
    for i in order:
        if _found(q, pages[i]):
            return Citation(source_id=source.id, page=i + 1, quote=q)
    for i in range(len(pages) - 1):
        if _found(q, pages[i] + " " + pages[i + 1]):
            return Citation(source_id=source.id, page=i + 1, quote=q)
    return None


def tagged_text(source: Source, max_chars: int = 90_000) -> str:
    """'[[p1]]\\n...\\n[[p2]]\\n...', truncated at a page boundary."""
    out: list[str] = []
    used = 0
    for n, page in enumerate(source.pages, 1):
        chunk = f"[[p{n}]]\n{page.strip()}"
        cost = len(chunk) + (2 if out else 0)
        if used + cost > max_chars:
            break
        out.append(chunk)
        used += cost
    return "\n\n".join(out)
