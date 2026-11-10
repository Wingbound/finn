# FINN Plan 7: End-of-day prices from NSE

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The daily refresh takes end-of-day prices from NSE's own MCP server, with Yahoo as the fallback per symbol. FINN's data is then NSE-sourced end to end: filings, XBRL results and prices.

**Why:** Yahoo is unofficial and rate-limits; its intraday bars needed `completed_sessions` to filter them. NSE's bhavcopy MCP is official, free, needs no key, and returned M&M's daily OHLCV through 9 Nov in under a second (checked 2026-11-10). The user approved the switch.

**Facts (probed 2026-11-10):**
- **Endpoint.** `https://mcp.nseindia.in/bhavcopy/cm/mcp`, MCP Streamable HTTP, protocol `2025-06-18`. `initialize` returns JSON and an `Mcp-Session-Id` header; `tools/call` answers as SSE (`event:message` / `data:{…}`).
- **The tool.** `get_stock_history` takes `{symbol, months ≤ 3}`. The tool result's text is JSON `{symbol, data: [{date, open, high, low, close, volume, series, …}]}`.
- **Unknown symbols.** The result text is `{"error": "Symbol not found: …"}`.
- **Fixtures.** Recorded responses are in `backend/tests/fixtures/nse_mcp/`.
- **Terms.** NSE's server describes its data as for "educational and research purposes only" and grants no commercial right. That's fine for this assignment. Say so in the README.

## Global constraints

- **Fallback.** Per symbol: a symbol NSE fails on (error, timeout, empty) is fetched from Yahoo. A fallback is not an error; only a symbol with no bars from either source is.
- **Provenance.** The summary records `price_sources` (`{"nse": n, "yahoo": m}`), and the store's meta records `prices_source`. `/portfolio` returns it as `source`, and the Alerts screen names it.
- **Tests stay offline.** An autouse fixture disables the NSE client. Respx serves the recorded fixtures in the client tests.

### Task 1: client, refresh, API, UI

- `finn/ingest/nse_mcp.py`:
  - `NseMcp(client, url)`, with `.open()` and `.call(tool, args) -> dict`, raising `NseMcpError`.
  - `fetch_nse_eod(holdings, months=3, client=None) -> tuple[list[PriceBar], dict[str, str]]`, returning the bars and the failures by symbol.
  - The client parses SSE or JSON and keeps the EQ series.
- `scripts/refresh.py`: NSE first, then Yahoo for the missing symbols only; record `price_sources` and the `prices_source` meta.
- `/portfolio` adds `source`; the Alerts holdings caption names the source.
- **Tests:**
  - the SSE fixture parses into the fixture's rows;
  - an unknown symbol becomes a failure;
  - initialize sends the protocol header and the session id is reused;
  - in the refresh, NSE gives some symbols and Yahoo is called with only the rest;
  - NSE fully down gives Yahoo for all, with no error;
  - both down keeps today's error;
  - `/portfolio` returns `source`;
  - the frontend caption.
