"""NSE corporate-announcements client and ingest."""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime

import httpx

from finn.db import set_meta, upsert_filings
from finn.models import IST, Filing

BASE_URL = "https://www.nseindia.com"
API_URL = f"{BASE_URL}/api/corporate-announcements"
INTEGRATED_URL = f"{BASE_URL}/api/integrated-filing-results"
INTEGRATED_TYPE = "Integrated Filing- Financials"
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
SYMBOL_PAUSE_S = 0.5  # polite gap between per-symbol requests
_sleep = time.sleep  # patched in tests

log = logging.getLogger(__name__)


class NSEUnavailable(Exception):
    """NSE could not be reached or kept refusing us."""


class PayloadTooLarge(NSEUnavailable):
    """The document exceeds the size cap. Permanent: retrying fetches the same bytes."""


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

    def _get(self, url: str, params: dict | None = None, check=None) -> httpx.Response:
        """GET with warm-up, 401/403 re-warm and backoff; `check(resp)` returns a reason to retry."""
        if not self._warmed:
            self._warm_up()
        last_error = "no attempts made"
        for attempt in range(self.max_retries):
            if attempt:
                _sleep(_BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)])
            try:
                resp = self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if resp.status_code in (401, 403):
                self._warm_up()
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue
            reason = check(resp) if check else None
            if reason:
                last_error = reason
                continue
            return resp
        raise NSEUnavailable(f"NSE request to {url} failed: {last_error}")

    def _get_json(self, url: str, params: dict | None, expect: type) -> object:
        parsed: list[object] = []

        def check(resp: httpx.Response) -> str | None:
            if "json" not in resp.headers.get("content-type", "").lower():
                return f"non-JSON content-type {resp.headers.get('content-type')!r}"
            try:
                data = resp.json()
            except ValueError:
                return "invalid JSON body"
            if not isinstance(data, expect):
                return f"unexpected JSON type {type(data).__name__}"
            parsed.append(data)
            return None

        self._get(url, params, check)
        return parsed[0]

    def fetch_announcements(self, symbol: str | None, start: date, end: date) -> list[dict]:
        params = {
            "index": "equities",
            "from_date": start.strftime("%d-%m-%Y"),
            "to_date": end.strftime("%d-%m-%Y"),
        }
        if symbol:
            params["symbol"] = symbol
        try:
            return self._get_json(API_URL, params, list)  # type: ignore[return-value]
        except NSEUnavailable as e:
            raise NSEUnavailable(
                f"NSE announcements for {symbol or 'all'} failed: {_reason(e)}"
            ) from e

    def fetch_integrated_financials(self, symbol: str) -> list[dict]:
        params = {"index": "equities", "symbol": symbol, "type": INTEGRATED_TYPE}
        try:
            body = self._get_json(INTEGRATED_URL, params, dict)
        except NSEUnavailable as e:
            raise NSEUnavailable(
                f"NSE integrated financials for {symbol} failed: {_reason(e)}"
            ) from e
        data = body.get("data")  # type: ignore[attr-defined]
        if not isinstance(data, list):
            raise NSEUnavailable(f"NSE integrated financials for {symbol}: no 'data' list")
        return data

    def fetch_bytes(self, url: str, max_bytes: int = 25_000_000) -> bytes:
        resp = self._get(url)
        declared = resp.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise PayloadTooLarge(f"{url} exceeds {max_bytes} bytes (content-length {declared})")
        if len(resp.content) > max_bytes:
            raise PayloadTooLarge(f"{url} exceeds {max_bytes} bytes ({len(resp.content)})")
        return resp.content


def _reason(e: NSEUnavailable) -> str:
    return str(e).split(" failed: ", 1)[-1]


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


@dataclass
class IngestResult:
    added: int = 0  # new rows stored
    skipped: int = 0  # malformed rows dropped
    failed: dict[str, str] = field(default_factory=dict)  # symbol -> why NSE gave up


def ingest_filings(
    conn: sqlite3.Connection,
    client: NSEClient,
    symbols: list[str],
    start: date,
    end: date,
) -> IngestResult:
    """Fetch and store filings symbol by symbol; never raises for NSE or row problems.

    Stored rows are never touched (INSERT OR IGNORE), so a failed symbol just keeps what it
    had. `filings_as_of` advances only when every symbol was fetched.
    """
    result = IngestResult()
    for i, symbol in enumerate(symbols):
        if i:
            _sleep(SYMBOL_PAUSE_S)
        try:
            rows = client.fetch_announcements(symbol, start, end)
        except NSEUnavailable as e:
            result.failed[symbol] = str(e)
            continue
        filings: list[Filing] = []
        for raw in rows:
            try:
                filings.append(parse_announcement(raw))
            except (KeyError, TypeError, ValueError) as e:  # ValidationError is a ValueError
                result.skipped += 1
                log.warning(
                    "skipping malformed NSE row for %s: %s: %s", symbol, type(e).__name__, e
                )
        result.added += upsert_filings(conn, filings)
    if not result.failed:
        set_meta(conn, "filings_as_of", datetime.now(IST).isoformat())
    return result
