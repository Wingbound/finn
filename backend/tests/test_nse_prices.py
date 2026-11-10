"""Plan 7: end-of-day prices from NSE's own MCP server, Yahoo as the per-symbol fallback."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from finn.ingest import nse_mcp
from finn.ingest.nse_mcp import MCP_URL, NseMcp, NseMcpError, fetch_nse_eod
from finn.portfolio import Holding

FIX = Path(__file__).parent / "fixtures" / "nse_mcp"
INIT = json.loads((FIX / "initialize.json").read_text())
RELIANCE_SSE = (FIX / "RELIANCE_history.sse").read_text()
UNKNOWN_SSE = (FIX / "unknown_symbol.sse").read_text()


def _holding(symbol: str) -> Holding:
    return Holding(symbol=symbol, name=symbol, sector="x", size="large", yahoo=f"{symbol}.NS")


def _server(seen: list[httpx.Request]):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        body = json.loads(req.content)
        if body.get("method") == "initialize":
            return httpx.Response(200, json=INIT, headers={"Mcp-Session-Id": "s-1"})
        if body.get("method") == "notifications/initialized":
            return httpx.Response(202)
        sym = body["params"]["arguments"]["symbol"]
        text = RELIANCE_SSE if sym == "RELIANCE" else UNKNOWN_SSE
        return httpx.Response(
            200, text=text, headers={"content-type": "text/event-stream;charset=UTF-8"}
        )

    return handler


@respx.mock
def test_history_parses_into_daily_bars():
    seen: list[httpx.Request] = []
    respx.post(MCP_URL).mock(side_effect=_server(seen))
    bars, failed = fetch_nse_eod([_holding("RELIANCE")], months=1)
    rows = json.loads(
        json.loads(RELIANCE_SSE.split("data:", 1)[1])["result"]["content"][0]["text"]
    )["data"]
    eq = [r for r in rows if r.get("series", "EQ") == "EQ"]
    assert failed == {} and len(bars) == len(eq)
    last = max(bars, key=lambda b: b.date)
    src = max(eq, key=lambda r: r["date"])
    assert (
        last.date == date.fromisoformat(src["date"])
        and last.close == src["close"]
        and last.volume == src["volume"]
    )
    assert all(b.symbol == "RELIANCE" for b in bars)


@respx.mock
def test_session_and_protocol_headers_are_sent():
    seen: list[httpx.Request] = []
    respx.post(MCP_URL).mock(side_effect=_server(seen))
    fetch_nse_eod([_holding("RELIANCE")], months=1)
    assert seen[0].headers["mcp-protocol-version"] == "2025-06-18"
    assert all(r.headers.get("mcp-session-id") == "s-1" for r in seen[1:])


@respx.mock
def test_an_unknown_symbol_is_a_failure_not_a_crash():
    seen: list[httpx.Request] = []
    respx.post(MCP_URL).mock(side_effect=_server(seen))
    bars, failed = fetch_nse_eod([_holding("RELIANCE"), _holding("NOSUCHSYM")], months=1)
    assert {b.symbol for b in bars} == {"RELIANCE"}
    assert "Symbol not found" in failed["NOSUCHSYM"]


@respx.mock
def test_a_server_that_is_down_fails_every_symbol():
    respx.post(MCP_URL).mock(return_value=httpx.Response(503))
    bars, failed = fetch_nse_eod([_holding("RELIANCE"), _holding("TCS")], months=1)
    assert bars == [] and set(failed) == {"RELIANCE", "TCS"}


def test_a_tool_error_raises():
    c = NseMcp(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    text='event:message\ndata:{"jsonrpc":"2.0","id":2,"error":{"code":-32603,"message":"boom"}}\n\n',
                    headers={"content-type": "text/event-stream"},
                )
            )
        )
    )
    c.session_id = "s"
    with pytest.raises(NseMcpError, match="boom"):
        c.call("get_stock_history", {"symbol": "X", "months": 1})


def test_module_exposes_the_documented_endpoint():
    assert nse_mcp.MCP_URL == "https://mcp.nseindia.in/bhavcopy/cm/mcp"


# ---- the refresh: NSE first, Yahoo for what NSE missed ----

import scripts.refresh as refresh_mod
from finn import db
from finn.config import Settings
from finn.enrich import EnrichResult
from finn.enrich import results as results_mod
from finn.ingest import nse as nse_ingest
from finn.models import PriceBar
from finn.portfolio import load_portfolio


def _bar(sym: str) -> PriceBar:
    return PriceBar(symbol=sym, date=date(2026, 11, 9), open=1, high=1, low=1, close=1, volume=1)


@pytest.fixture
def quiet(monkeypatch):
    settings = Settings(_env_file=None, gemini_api_key="", groq_api_key="")
    monkeypatch.setattr(refresh_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(refresh_mod, "ingest_filings", lambda *a, **k: nse_ingest.IngestResult())
    monkeypatch.setattr(
        refresh_mod, "ingest_financials", lambda *a, **k: results_mod.FinancialsResult()
    )
    monkeypatch.setattr(refresh_mod, "enrich_people", lambda *a, **k: EnrichResult())
    monkeypatch.setattr(refresh_mod, "enrich_briefs", lambda *a, **k: EnrichResult())


def test_refresh_takes_nse_first_and_yahoo_for_the_rest(conn, quiet, monkeypatch):
    holdings = load_portfolio()
    nse_syms = {h.symbol for h in holdings[:15]}
    monkeypatch.setattr(
        refresh_mod,
        "fetch_nse_eod",
        lambda hs, **k: (
            [_bar(h.symbol) for h in hs if h.symbol in nse_syms],
            {h.symbol: "x" for h in hs if h.symbol not in nse_syms},
        ),
    )
    asked: list[str] = []

    def yahoo(hs, **_):
        asked.extend(h.symbol for h in hs)
        return [_bar(h.symbol) for h in hs]

    monkeypatch.setattr(refresh_mod, "fetch_eod", yahoo)
    summary = refresh_mod.refresh(conn, use_llm=False)
    assert sorted(asked) == sorted(h.symbol for h in holdings[15:])
    assert summary["price_sources"] == {"nse": 15, "yahoo": len(holdings) - 15}
    assert summary["errors"] == [] and summary["prices_missing"] == []
    assert db.get_meta(conn, "prices_source") == "NSE end-of-day (Yahoo for 3)"


def test_refresh_falls_back_to_yahoo_entirely_without_an_error(conn, quiet, monkeypatch):
    monkeypatch.setattr(
        refresh_mod, "fetch_nse_eod", lambda hs, **k: ([], {h.symbol: "down" for h in hs})
    )
    monkeypatch.setattr(refresh_mod, "fetch_eod", lambda hs, **_: [_bar(h.symbol) for h in hs])
    summary = refresh_mod.refresh(conn, use_llm=False)
    assert summary["errors"] == [] and summary["price_sources"]["nse"] == 0
    assert db.get_meta(conn, "prices_source") == "Yahoo end-of-day"


def test_refresh_with_both_sources_down_is_still_an_error(conn, quiet, monkeypatch):
    monkeypatch.setattr(
        refresh_mod, "fetch_nse_eod", lambda hs, **k: ([], {h.symbol: "down" for h in hs})
    )

    def boom(*a, **k):
        raise ConnectionError("yahoo said no")

    monkeypatch.setattr(refresh_mod, "fetch_eod", boom)
    summary = refresh_mod.refresh(conn, use_llm=False)
    assert any("yahoo said no" in e for e in summary["errors"])
    assert summary["price_bars"] == 0


def test_portfolio_names_its_price_source(tmp_path):
    from fastapi.testclient import TestClient

    from finn.api import main as api_main
    from finn.api.deps import get_conn

    path = tmp_path / "p.sqlite"
    c = db.connect(path)
    db.init_db(c)
    db.set_meta(c, "prices_source", "NSE end-of-day")
    c.close()

    def _c():
        cc = db.connect(path)
        try:
            yield cc
        finally:
            cc.close()

    api_main.app.dependency_overrides[get_conn] = _c
    try:
        assert TestClient(api_main.app).get("/portfolio").json()["source"] == "NSE end-of-day"
    finally:
        api_main.app.dependency_overrides.clear()
