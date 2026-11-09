"""Grounding guard: nothing an LLM says is shown unless the filing text says it too."""

from __future__ import annotations

import re
import unicodedata

_QUOTES = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
    }
)
HONORIFICS = re.compile(r"^(?:(?:mr|mrs|ms|dr|shri|smt)\.?(?:\s+|$))+", re.IGNORECASE)
# Split after . ! ? but not after an honorific abbreviation such as "Mr."
_SENTENCE_SPLIT = re.compile(r"(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSmt)(?<=[.!?])\s+")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize(s: str) -> str:
    """NFKC, curly quotes to straight, whitespace collapsed, casefolded."""
    s = unicodedata.normalize("NFKC", s).translate(_QUOTES)
    return " ".join(s.split()).casefold()


def strip_honorifics(name: str) -> str:
    return HONORIFICS.sub("", name.strip())


def name_in_text(name: str, text: str) -> bool:
    """True if the name, minus leading honorifics, appears in the text."""
    bare = normalize(strip_honorifics(name))
    return bool(bare) and bare in normalize(text)


def grounded_sentences(passage: str, text: str, max_words: int) -> str | None:
    """Sentences of passage that occur verbatim (after normalize) in text, or None.

    Whole kept sentences are joined in order until adding the next would exceed max_words.
    If even the first kept sentence exceeds max_words, only that sentence is returned,
    cut to max_words words and followed by "…".
    """
    haystack = normalize(text)
    kept = [
        s
        for s in (p.strip() for p in _SENTENCE_SPLIT.split(passage or ""))
        if s and normalize(s) in haystack
    ]
    if not kept:
        return None
    out: list[str] = []
    words = 0
    for s in kept:
        n = len(s.split())
        if words + n > max_words:
            break
        out.append(s)
        words += n
    if out:
        return " ".join(out)
    return " ".join(kept[0].split()[:max_words]) + "…"


def _numbers(s: str) -> set[str]:
    return {m.replace(",", "") for m in _NUMBER.findall(s)}


def numbers_grounded(s: str, text: str) -> bool:
    """Every number in s (commas ignored, years included) also appears as a number in text."""
    return _numbers(s) <= _numbers(text)
