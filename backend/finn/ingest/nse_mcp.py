"""End-of-day prices from NSE's own MCP server (the bhavcopy service).

NSE publishes official daily OHLCV for its listed equities through a free, keyless MCP server
(Streamable HTTP, protocol 2025-06-18). FINN calls its `get_stock_history` tool directly over
JSON-RPC; no MCP SDK is needed. NSE describes the data as for educational and research use.

`initialize` answers in JSON with an `Mcp-Session-Id` header; `tools/call` answers as SSE
(`event:message` / `data:{…}`). A symbol NSE doesn't know comes back as a *successful* result
whose text is `{"error": "Symbol not found: …"}`, so every result is checked.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import httpx

from finn.models import PriceBar
from finn.portfolio import Holding

log = logging.getLogger(__name__)

MCP_URL = "https://mcp.nseindia.in/bhavcopy/cm/mcp"
PROTOCOL = "2025-06-18"
TIMEOUT_S = 20.0
MAX_MONTHS = 3  # the tool's own cap per call; 3 months covers the 20-session volume baseline
MIN_SESSIONS = 40  # fewer than this and the alert baseline is thin: let the fallback try
STALE_DAYS = 7  # a last session older than this is not today's end-of-day data
BREAKER_FAILURES = 3  # consecutive transport failures before NSE is skipped for this run


@dataclass
class NseResult:
    """What NSE gave: usable bars, why other symbols failed, and thin or stale bars kept in
    case the fallback has nothing better."""

    bars: list[PriceBar]
    failed: dict[str, str]
    partial: dict[str, list[PriceBar]] = field(default_factory=dict)


class NseMcpError(Exception):
    """The NSE MCP server could not answer a call."""


def _payload(resp: httpx.Response) -> dict | None:
    """The JSON-RPC message from a JSON or SSE response (the last `data:` line wins)."""
    text = resp.text.strip()
    if not text:
        return None
    if "text/event-stream" in resp.headers.get("content-type", "") or text.startswith("event:"):
        data = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
        if not data:
            return None
        text = data[-1]
    return json.loads(text)


class NseMcp:
    """A minimal MCP client: one session, tool calls returning their JSON text as a dict."""

    def __init__(self, client: httpx.Client, url: str = MCP_URL):
        self.client = client
        self.url = url
        self.session_id: str | None = None
        self._id = 0

    def _post(self, body: dict) -> httpx.Response:
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": PROTOCOL,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        resp = self.client.post(self.url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise NseMcpError(f"NSE MCP answered {resp.status_code}")
        return resp

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def open(self) -> None:
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "finn", "version": "1.0"},
                },
            }
        )
        self.session_id = resp.headers.get("mcp-session-id")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, tool: str, args: dict) -> dict:
        msg = _payload(
            self._post(
                {
                    "jsonrpc": "2.0",
                    "id": self._next_id(),
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": args},
                }
            )
        )
        if not isinstance(msg, dict):
            raise NseMcpError(f"{tool}: empty or unexpected answer")
        if msg.get("error"):
            err = msg["error"]
            raise NseMcpError(
                f"{tool}: {err.get('message', err) if isinstance(err, dict) else err}"
            )
        result = msg.get("result") if isinstance(msg.get("result"), dict) else {}
        content = result.get("content") if isinstance(result.get("content"), list) else []
        texts = [
            c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
        ]
        if result.get("isError") or not texts:
            raise NseMcpError(f"{tool}: {' '.join(texts) or 'no content'}")
        try:
            out = json.loads(texts[0])
        except json.JSONDecodeError as e:
            raise NseMcpError(f"{tool}: not JSON: {texts[0][:120]}") from e
        if not isinstance(out, dict):
            raise NseMcpError(f"{tool}: unexpected result shape")
        if out.get("error"):
            raise NseMcpError(str(out["error"]))
        return out


def _bars(symbol: str, payload: dict) -> list[PriceBar]:
    rows = payload.get("data") or []
    eq = [r for r in rows if r.get("series", "EQ") == "EQ"] or rows
    bars = []
    for r in eq:
        try:
            bars.append(
                PriceBar(
                    symbol=symbol,
                    date=date.fromisoformat(r["date"]),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=int(r["volume"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue  # one malformed row must not cost the symbol its history
    return bars


def fetch_nse_eod(
    holdings: list[Holding],
    months: int = MAX_MONTHS,
    client: httpx.Client | None = None,
    today: date | None = None,
) -> NseResult:
    """Daily bars per holding from NSE. A symbol whose history is thin (under MIN_SESSIONS) or
    stale (last session over STALE_DAYS old) counts as failed, with its bars kept in
    `partial`, so the caller can try another source first. After BREAKER_FAILURES transport
    failures in a row the rest are failed at once: a hung server must not stall the refresh."""
    today = today or datetime.now().date()
    own = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S)
    out = NseResult(bars=[], failed={}, partial={})
    try:
        mcp = NseMcp(http)
        try:
            mcp.open()
        except (NseMcpError, httpx.HTTPError, ValueError) as e:
            out.failed = {h.symbol: f"NSE MCP unavailable: {e}" for h in holdings}
            return out
        streak = 0
        for h in holdings:
            if streak >= BREAKER_FAILURES:
                out.failed[h.symbol] = "skipped: NSE MCP stopped answering"
                continue
            args = {"symbol": h.symbol, "months": min(months, MAX_MONTHS)}
            try:
                got = _bars(h.symbol, mcp.call("get_stock_history", args))
            except httpx.HTTPError as e:
                streak += 1
                out.failed[h.symbol] = f"{type(e).__name__}: {e}"
                continue
            except (NseMcpError, ValueError) as e:
                streak = 0  # the server answered; this symbol is the problem
                out.failed[h.symbol] = str(e)
                continue
            streak = 0
            if not got:
                out.failed[h.symbol] = "no bars returned"
                continue
            last = max(b.date for b in got)
            if len(got) < min(MIN_SESSIONS, 20 * min(months, MAX_MONTHS)):
                out.failed[h.symbol] = f"only {len(got)} sessions"
                out.partial[h.symbol] = got
            elif (today - last) > timedelta(days=STALE_DAYS):
                out.failed[h.symbol] = f"last session {last.isoformat()}"
                out.partial[h.symbol] = got
            else:
                out.bars.extend(got)
    finally:
        if own:
            http.close()
    return out
