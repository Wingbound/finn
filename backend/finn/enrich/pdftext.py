"""Filing PDF text extraction, caching and relevance windowing."""

from __future__ import annotations

import io
import logging
import sqlite3

from pypdf import PdfReader

from finn import db

log = logging.getLogger(__name__)

_BEFORE, _AFTER = 8, 30


def extract_text(pdf: bytes) -> str:
    """Text of all pages joined by newline; "" for anything unreadable. Never raises."""
    pypdf_log = logging.getLogger("pypdf")
    prev = pypdf_log.level
    pypdf_log.setLevel(logging.CRITICAL)
    try:
        reader = PdfReader(io.BytesIO(pdf))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:  # noqa: BLE001 - malformed input of any kind must yield ""
        log.debug("pdf extraction failed: %s", e)
        return ""
    finally:
        pypdf_log.setLevel(prev)


def get_doc_text(conn: sqlite3.Connection, client, url: str, max_bytes: int = 25_000_000) -> str:
    """PDF text for url, cached. Fetch errors (NSEUnavailable) propagate uncached."""
    cached = db.get_doc_text_cached(conn, url)
    if cached is not None:
        return cached
    text = extract_text(client.fetch_bytes(url, max_bytes=max_bytes))
    db.save_doc_text(conn, url, text)
    return text


def relevant_window(text: str, terms: list[str], max_chars: int = 12_000) -> str:
    """Passages around term hits, capped at max_chars; head of text if nothing hits."""
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    needles = [t.lower() for t in terms if t]
    spans: list[list[int]] = []
    for i, line in enumerate(lines):
        low = line.lower()
        if any(n in low for n in needles):
            lo, hi = max(0, i - _BEFORE), min(len(lines), i + _AFTER + 1)
            if spans and lo <= spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], hi)
            else:
                spans.append([lo, hi])
    if not spans:
        return text[:max_chars]
    return "\n…\n".join("\n".join(lines[lo:hi]) for lo, hi in spans)[:max_chars]
