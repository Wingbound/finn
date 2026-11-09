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
_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "shri.", "smt.", "prof.", "ltd.", "pvt.", "co.", "no.",
    "viz.", "i.e.", "e.g.",
}  # fmt: skip
_INITIALS = re.compile(r"^(?:[A-Za-z]\.)+$")  # "N.", "C.P."
_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
MIN_SENTENCE_WORDS = 4
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize(s: str) -> str:
    """NFKC, curly quotes to straight, whitespace collapsed, casefolded."""
    s = unicodedata.normalize("NFKC", s).translate(_QUOTES)
    return " ".join(s.split()).casefold()


def strip_honorifics(name: str) -> str:
    return HONORIFICS.sub("", name.strip())


def name_in_text(name: str, text: str) -> bool:
    """True if the name, minus leading honorifics, has at least 2 tokens and appears in the
    text on word boundaries."""
    bare = normalize(strip_honorifics(name))
    if len(bare.split()) < 2:
        return False
    return re.search(r"(?<!\w)" + re.escape(bare) + r"(?!\w)", normalize(text)) is not None


def split_sentences(passage: str) -> list[str]:
    """Split after . ! ? but never after an honorific/abbreviation or a capital initial."""
    out: list[str] = []
    carry = ""
    for piece in _BOUNDARY.split(passage.strip()):
        cur = f"{carry} {piece}".strip() if carry else piece
        last = cur.split()[-1] if cur.split() else ""
        if last.lower() in _ABBREVIATIONS or _INITIALS.match(last):
            carry = cur
            continue
        carry = ""
        out.append(cur)
    if carry:
        out.append(carry)
    return out


def grounded_sentences(passage: str, text: str, max_words: int) -> str | None:
    """Sentences of passage that occur verbatim (after normalize) in text, or None.

    Sentences under 4 words are dropped. Whole kept sentences are joined in order until adding the next would exceed max_words.
    If even the first kept sentence exceeds max_words, only that sentence is returned,
    cut to max_words words and followed by "…".
    """
    haystack = normalize(text)
    kept = [
        s
        for s in split_sentences(passage or "")
        if len(s.split()) >= MIN_SENTENCE_WORDS and normalize(s) in haystack
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
