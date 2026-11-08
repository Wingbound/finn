"""NSE corporate-announcements client and ingest."""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime

import httpx

from finn.db import set_meta, upsert_filings
from finn.models import IST, Filing

BASE_URL = "https://www.nseindia.com"
API_URL = f"{BASE_URL}/api/corporate-announcements"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE_URL}/",
}
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
_sleep = time.sleep  # patched in tests


class NSEUnavailable(Exception):
    """NSE could not be reached or kept refusing us."""


class NSEClient:
    def __init__(self, timeout: float = 30, max_retries: int = 3):
        self.max_retries = max_retries
        self._http = httpx.Client(timeout=timeout, headers=HEADERS, follow_redirects=True)
        self._warmed = False

    def close(self) -> None:
        self._http.close()

    def _warm_up(self) -> None:
        """Visit the home page to collect cookies; a 403 or network error is fine."""
        try:
            self._http.get(f"{BASE_URL}/")
        except httpx.HTTPError:
            pass
        self._warmed = True

    def fetch_announcements(self, symbol: str | None, start: date, end: date) -> list[dict]:
        params = {
            "index": "equities",
            "from_date": start.strftime("%d-%m-%Y"),
            "to_date": end.strftime("%d-%m-%Y"),
        }
        if symbol:
            params["symbol"] = symbol
        if not self._warmed:
            self._warm_up()
        last_error = "no attempts made"
        for attempt in range(self.max_retries):
            if attempt:
                _sleep(_BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)])
            try:
                resp = self._http.get(API_URL, params=params)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if resp.status_code in (401, 403):
                self._warm_up()
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue
            if "json" not in resp.headers.get("content-type", "").lower():
                last_error = f"non-JSON content-type {resp.headers.get('content-type')!r}"
                continue
            try:
                data = resp.json()
            except ValueError:
                last_error = "invalid JSON body"
                continue
            if not isinstance(data, list):
                last_error = f"unexpected JSON type {type(data).__name__}"
                continue
            return data
        raise NSEUnavailable(f"NSE announcements for {symbol or 'all'} failed: {last_error}")


def parse_announcement(raw: dict) -> Filing:
    filed_at = datetime.strptime(raw["an_dt"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    return Filing(
        seq_id=str(raw["seq_id"]),
        symbol=raw["symbol"],
        company=raw.get("sm_name") or raw["symbol"],
        nse_desc=raw.get("desc") or "",
        subject=raw.get("attchmntText") or "",
        nse_summary=raw.get("voiceSummary") or None,
        pdf_url=raw.get("attchmntFile") or None,
        filed_at=filed_at,
        has_xbrl=bool(raw.get("hasXbrl")),
    )


def ingest_filings(
    conn: sqlite3.Connection,
    client: NSEClient,
    symbols: list[str],
    start: date,
    end: date,
) -> int:
    """Fetch every symbol first; write nothing unless all succeed. Returns new rows."""
    filings: list[Filing] = []
    for symbol in symbols:
        filings.extend(parse_announcement(r) for r in client.fetch_announcements(symbol, start, end))
    added = upsert_filings(conn, filings)
    set_meta(conn, "filings_as_of", datetime.now(IST).isoformat())
    return added
