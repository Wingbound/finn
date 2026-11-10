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
from datetime import date

import httpx

from finn.models import PriceBar
from finn.portfolio import Holding

log = logging.getLogger(__name__)

MCP_URL = "https://mcp.nseindia.in/bhavcopy/cm/mcp"
PROTOCOL = "2025-06-18"
TIMEOUT_S = 20.0
MAX_MONTHS = 3  # the tool's own cap per call; 3 months covers the 20-session volume baseline


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
        if not msg:
            raise NseMcpError(f"{tool}: empty answer")
        if "error" in msg:
            raise NseMcpError(f"{tool}: {msg['error'].get('message', msg['error'])}")
        result = msg.get("result") or {}
        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        if result.get("isError") or not texts:
            raise NseMcpError(f"{tool}: {' '.join(texts) or 'no content'}")
        try:
            out = json.loads(texts[0])
        except json.JSONDecodeError as e:
            raise NseMcpError(f"{tool}: not JSON: {texts[0][:120]}") from e
        if isinstance(out, dict) and out.get("error"):
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
    holdings: list[Holding], months: int = MAX_MONTHS, client: httpx.Client | None = None
) -> tuple[list[PriceBar], dict[str, str]]:
    """Daily bars for each holding from NSE, and why each symbol that got none failed."""
    own = client is None
    http = client or httpx.Client(timeout=TIMEOUT_S)
    bars: list[PriceBar] = []
    failed: dict[str, str] = {}
    try:
        mcp = NseMcp(http)
        try:
            mcp.open()
        except (NseMcpError, httpx.HTTPError, ValueError) as e:
            return [], {h.symbol: f"NSE MCP unavailable: {e}" for h in holdings}
        for h in holdings:
            try:
                got = _bars(
                    h.symbol,
                    mcp.call(
                        "get_stock_history", {"symbol": h.symbol, "months": min(months, MAX_MONTHS)}
                    ),
                )
            except (NseMcpError, httpx.HTTPError, ValueError) as e:
                failed[h.symbol] = str(e)
                continue
            if got:
                bars.extend(got)
            else:
                failed[h.symbol] = "no bars returned"
    finally:
        if own:
            http.close()
    return bars, failed
