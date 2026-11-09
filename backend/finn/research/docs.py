"""Transcript and annual-report sources with per-page text cached in SQLite."""

from __future__ import annotations

import io
import logging
import sqlite3
import time
from collections.abc import Callable
from typing import Self
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader

from finn import db
from finn.models import Source

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
_RETRIES = 2
MAX_TRANSCRIPTS = 4
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


class DocError(Exception):
    """A document could not be downloaded or is not a usable PDF."""


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


class DocClient:
    """httpx wrapper for PDF downloads. The caller owns it: close() or use `with`."""

    def __init__(self, timeout: float = 60.0, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            timeout=timeout, follow_redirects=True, transport=transport, headers={"User-Agent": _UA}
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def fetch_bytes(self, url: str, max_bytes: int = 40_000_000) -> bytes:
        headers = {}
        host = urlparse(url).hostname or ""
        if host.endswith("bseindia.com"):
            headers["Referer"] = "https://www.bseindia.com/"
        last = "no attempt"
        for attempt in range(_RETRIES + 1):
            if attempt:
                _sleep(0.5 * attempt)
            try:
                r = self._http.get(url, headers=headers)
            except httpx.HTTPError as e:
                last = f"{type(e).__name__}: {e}"
                continue
            if r.status_code != 200:
                last = f"HTTP {r.status_code}"
                if r.status_code < 500 and r.status_code != 429:
                    break
                continue
            body = r.content
            if len(body) > max_bytes:
                raise DocError(f"{url} is larger than {max_bytes} bytes")
            if not body.startswith(b"%PDF"):
                raise DocError(f"{url} is not a PDF")
            return body
        raise DocError(f"{url}: {last}")


def call_quarter(date_label: str) -> str:
    """Quarter reported on a call held in this month: "Oct 2026" -> "Q2 FY27".

    Raises ValueError on an unparseable label.
    """
    mon, year = date_label.split()
    m, y = _MONTHS.index(mon[:3].lower()) + 1, int(year)
    if m <= 3:
        return f"Q3 FY{y % 100:02d}"
    if m <= 6:
        return f"Q4 FY{y % 100:02d}"
    if m <= 9:
        return f"Q1 FY{(y + 1) % 100:02d}"
    return f"Q2 FY{(y + 1) % 100:02d}"


def pdf_pages(pdf: bytes, max_pages: int | None = None) -> list[str]:
    """Text per page (pages[0] is page 1). [] for anything unreadable. Never raises."""
    pypdf_log = logging.getLogger("pypdf")
    prev = pypdf_log.level
    pypdf_log.setLevel(logging.CRITICAL)
    try:
        reader = PdfReader(io.BytesIO(pdf))
        out = []
        for i, page in enumerate(reader.pages):
            if max_pages is not None and i >= max_pages:
                break
            out.append(page.extract_text() or "")
        return out
    except Exception as e:  # noqa: BLE001 - malformed input of any kind must yield []
        log.debug("pdf page extraction failed: %s", e)
        return []
    finally:
        pypdf_log.setLevel(prev)


def get_pages(
    conn: sqlite3.Connection, client: DocClient, url: str, max_pages: int | None = None
) -> list[str]:
    """Page texts for url, cached. DocError propagates uncached; unreadable PDFs cache []."""
    cached = db.get_doc_pages(conn, url)
    if cached is not None:
        return cached
    pages = pdf_pages(client.fetch_bytes(url), max_pages)
    db.save_doc_pages(conn, url, pages)
    return pages


def collect_sources(
    conn: sqlite3.Connection,
    client: DocClient,
    documents: dict,
    max_transcripts: int = MAX_TRANSCRIPTS,
    ar_pages: int = 40,
    progress: Callable[[str], None] = lambda m: None,
    deadline: float | None = None,
    now: Callable[[], float] = time.monotonic,
) -> tuple[list[Source], list[str]]:
    """Read the latest transcripts and annual report. Past `deadline` (on the `now` clock) no
    further source is read and one note says so."""
    sources: list[Source] = []
    notes: list[str] = []

    def late() -> bool:
        if deadline is not None and now() > deadline:
            notes.append("Remaining sources skipped: build deadline reached")
            return True
        return False

    n = 0
    for call in documents.get("concalls", []):
        if n >= max_transcripts:
            break
        url = call.get("transcript_url")
        if not url:
            continue  # not posted yet
        if late():
            return sources, notes
        n += 1
        label = "unknown"
        try:
            date = call["date"]
            label = date
            quarter = call_quarter(date)
            title = f"{quarter} earnings call ({date})"
            progress(f"Reading {title}")
            try:
                pages = get_pages(conn, client, url)
            except DocError as e:
                notes.append(f"{date} transcript unavailable: {e}")
                continue
            if not any(p.strip() for p in pages):
                notes.append(f"{date} transcript unavailable: no extractable text")
                continue
            sources.append(
                Source(
                    id=f"T{len(sources) + 1}",
                    kind="transcript",
                    title=title,
                    quarter=quarter,
                    url=url,
                    pages=pages,
                )
            )
        except Exception as e:  # noqa: BLE001 - one odd row must not abort the whole collection
            notes.append(f"{label} skipped: {type(e).__name__}: {e}")
    reports = documents.get("annual_reports", [])
    if reports and not late():
        try:
            ar = reports[0]
            title = f"Annual Report {ar['year']}"
            progress(f"Reading {title}")
            try:
                pages = get_pages(conn, client, ar["url"], max_pages=ar_pages)
            except DocError as e:
                notes.append(f"Annual report {ar['year']} unavailable: {e}")
            else:
                if any(p.strip() for p in pages):
                    sources.append(
                        Source(
                            id="AR",
                            kind="annual_report",
                            title=title,
                            quarter=None,
                            url=ar["url"],
                            pages=pages,
                        )
                    )
                else:
                    notes.append(f"Annual report {ar['year']} unavailable: no extractable text")
        except Exception as e:  # noqa: BLE001 - one odd row must not abort the whole collection
            notes.append(f"annual report skipped: {type(e).__name__}: {e}")
    return sources, notes
