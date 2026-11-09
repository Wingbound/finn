import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest
import respx

from finn import db
from finn.config import Settings
from finn.enrich import EnrichResult
from finn.enrich import results as results_mod
from finn.ingest import nse
from finn.models import IST, PriceBar
from finn.portfolio import load_portfolio
from scripts import refresh as refresh_mod
from scripts.refresh import refresh

FIX = Path(__file__).parent / "fixtures" / "nse"
NSE_API = "https://www.nseindia.com/api/corporate-announcements"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(nse, "_sleep", lambda s: None)


@pytest.fixture(autouse=True)
def no_enrichment(monkeypatch):
    """Existing tests cover filings/prices/classify; the new stages are stubbed out here and
    switched on (via `real_financials`) in the tests that exercise them."""
    monkeypatch.setattr(
        refresh_mod, "ingest_financials", lambda *a, **k: results_mod.FinancialsResult()
    )
    monkeypatch.setattr(refresh_mod, "enrich_people", lambda *a, **k: EnrichResult())
    monkeypatch.setattr(refresh_mod, "enrich_briefs", lambda *a, **k: EnrichResult())


@pytest.fixture
def keyless(monkeypatch):
    settings = Settings(_env_file=None, gemini_api_key="", groq_api_key="")
    monkeypatch.setattr(refresh_mod, "get_settings", lambda: settings)


@pytest.fixture
def month_by_symbol():
    by_symbol = defaultdict(list)
    for r in json.loads((FIX / "portfolio_month.json").read_text()):
        by_symbol[r["symbol"]].append(r)
    return by_symbol


def _nse_ok(month_by_symbol):
    respx.get("https://www.nseindia.com/").respond(200)
    respx.get(NSE_API).mock(
        side_effect=lambda req: httpx.Response(
            200, json=month_by_symbol.get(req.url.params["symbol"], [])
        )
    )


def _bars(holdings, **_):
    return [
        PriceBar(symbol=h.symbol, date=date(2026, 11, 6), open=1, high=1, low=1, close=1, volume=1)
        for h in holdings
    ]


@respx.mock
def test_refresh_ingests_prices_and_classifies(conn, keyless, month_by_symbol, monkeypatch):
    _nse_ok(month_by_symbol)
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    summary = refresh(conn, days=30, use_llm=False)
    assert summary["filings_new"] == 323
    assert summary["price_bars"] == 18 and summary["price_symbols"] == 18
    assert sum(summary["classify"].values()) == 323
    assert summary["classify"]["llm"] == 0
    assert summary["unclassified_left"] == 0
    assert summary["errors"] == []
    assert summary["filings_skipped"] == 0 and summary["prices_missing"] == []
    assert db.get_meta(conn, "filings_as_of") and db.get_meta(conn, "prices_as_of")
    assert {h.symbol for h in load_portfolio()} == {
        r["symbol"] for r in conn.execute("SELECT DISTINCT symbol FROM prices")
    }


@respx.mock
def test_nse_unavailable_keeps_filings_and_still_fetches_prices(
    conn, keyless, month_by_symbol, monkeypatch, capsys
):
    _nse_ok(month_by_symbol)
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    refresh(conn, use_llm=False)
    as_of = db.get_meta(conn, "filings_as_of")

    respx.get(NSE_API).respond(403)
    summary = refresh(conn, use_llm=False)
    assert summary["filings_new"] == 0
    assert summary["filings_total"] == 323
    assert len(summary["errors"]) == 18
    assert all(e.startswith("filings: NSE") for e in summary["errors"])
    assert db.get_meta(conn, "filings_as_of") == as_of  # not advanced
    assert summary["price_bars"] == 18
    assert "NSE" in capsys.readouterr().out


@respx.mock
def test_one_symbol_failing_keeps_the_rest_and_holds_filings_as_of(
    conn, keyless, month_by_symbol, monkeypatch
):
    respx.get("https://www.nseindia.com/").respond(200)
    respx.get(NSE_API).mock(
        side_effect=lambda req: (
            httpx.Response(403)
            if req.url.params["symbol"] == "TRENT"
            else httpx.Response(200, json=month_by_symbol.get(req.url.params["symbol"], []))
        )
    )
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    summary = refresh(conn, use_llm=False)
    assert summary["filings_new"] == 323 - len(month_by_symbol["TRENT"]) > 0
    assert len(summary["errors"]) == 1 and "TRENT" in summary["errors"][0]
    assert db.get_meta(conn, "filings_as_of") is None
    assert summary["price_bars"] == 18


@respx.mock
def test_prices_still_run_when_the_filings_stage_crashes(conn, keyless, monkeypatch):
    def crash(*a, **k):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(refresh_mod, "ingest_filings", crash)
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    summary = refresh(conn, use_llm=False)
    assert summary["errors"] == ["filings: RuntimeError: parser exploded"]
    assert summary["price_bars"] == 18 and db.get_meta(conn, "prices_as_of")


@respx.mock
def test_prices_as_of_is_fetch_time_and_missing_symbols_listed(
    conn, keyless, month_by_symbol, monkeypatch
):
    _nse_ok(month_by_symbol)
    fetched = []

    def partial(holdings, **_):
        fetched.append(datetime.now(IST))
        return _bars([h for h in holdings if h.symbol not in {"AMBER", "LODHA"}])

    monkeypatch.setattr(refresh_mod, "fetch_eod", partial)
    summary = refresh(conn, use_llm=False)
    assert summary["prices_missing"] == ["AMBER", "LODHA"]
    assert summary["errors"] == ["prices: no bars for AMBER, LODHA"]
    as_of = datetime.fromisoformat(db.get_meta(conn, "prices_as_of"))
    assert fetched[0] <= as_of <= datetime.now(IST)  # a fetch timestamp, not a bar date


@respx.mock
def test_price_failure_is_reported_and_prices_as_of_not_set(
    conn, keyless, month_by_symbol, monkeypatch
):
    _nse_ok(month_by_symbol)

    def boom(holdings, **_):
        raise ConnectionError("yahoo said no")

    monkeypatch.setattr(refresh_mod, "fetch_eod", boom)
    summary = refresh(conn, use_llm=False)
    assert summary["filings_new"] == 323 and summary["unclassified_left"] == 0
    assert summary["price_bars"] == 0
    assert any("yahoo said no" in e for e in summary["errors"])
    assert db.get_meta(conn, "prices_as_of") is None


@respx.mock
def test_empty_price_frame_is_an_error(conn, keyless, month_by_symbol, monkeypatch):
    _nse_ok(month_by_symbol)
    monkeypatch.setattr(refresh_mod, "fetch_eod", lambda holdings, **_: [])
    summary = refresh(conn, use_llm=False)
    assert any(e.startswith("prices") for e in summary["errors"])
    assert db.get_meta(conn, "prices_as_of") is None


@respx.mock
def test_use_llm_without_keys_degrades_to_rules(
    conn, keyless, month_by_symbol, monkeypatch, capsys
):
    _nse_ok(month_by_symbol)
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    summary = refresh(conn, use_llm=True)
    assert summary["classify"]["llm"] == 0 and summary["classify"]["default"] > 0
    assert summary["unclassified_left"] == 0
    assert "GROQ_API_KEY" in capsys.readouterr().out


def _groq(req):
    ids = [item["id"] for item in json.loads(json.loads(req.content)["messages"][1]["content"])]
    items = [{"id": i, "category": "press_release", "subtype": None} for i in ids]
    content = json.dumps({"items": items})
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _keyed(monkeypatch):
    settings = Settings(_env_file=None, gemini_api_key="", groq_api_key="test-key")
    monkeypatch.setattr(refresh_mod, "get_settings", lambda: settings)


@respx.mock
def test_use_llm_with_key_sends_rule_misses_to_llm(conn, month_by_symbol, monkeypatch):
    _keyed(monkeypatch)
    _nse_ok(month_by_symbol)
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    respx.post(GROQ_URL).mock(side_effect=_groq)
    summary = refresh(conn, use_llm=True)
    assert summary["classify"]["llm"] > 0 and summary["classify"]["default"] == 0
    assert summary["llm"]["calls"] > 0


@respx.mock
def test_keyed_refresh_upgrades_rows_defaulted_by_a_keyless_run(
    conn, keyless, month_by_symbol, monkeypatch
):
    _nse_ok(month_by_symbol)
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    first = refresh(conn, use_llm=False)  # e.g. the seed, built before keys existed
    assert first["classify"]["default"] > 0

    _keyed(monkeypatch)
    respx.post(GROQ_URL).mock(side_effect=_groq)
    second = refresh(conn, use_llm=True)
    assert second["filings_new"] == 0
    assert second["classify"] == {"rules": 0, "llm": first["classify"]["default"], "default": 0}
    assert db.default_classified_filings(conn) == []


@respx.mock
def test_cli_writes_out_path_without_wal_files(tmp_path, keyless, month_by_symbol, monkeypatch):
    _nse_ok(month_by_symbol)
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    out = tmp_path / "seed" / "finn.sqlite"
    assert refresh_mod.main(["--days", "30", "--no-llm", "--out", str(out)]) == 0
    assert out.exists()
    assert not (tmp_path / "seed" / "finn.sqlite-wal").exists()
    c = db.connect(out)
    assert c.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 323
    c.close()


@pytest.fixture
def fin_env(monkeypatch):
    monkeypatch.setattr(results_mod, "_sleep", lambda s: None)
    monkeypatch.setattr(refresh_mod, "ingest_financials", results_mod.ingest_financials)
    monkeypatch.setattr(refresh_mod, "fetch_eod", _bars)
    monkeypatch.setattr(refresh_mod, "ingest_filings", lambda *a, **k: nse.IngestResult())


def test_refresh_runs_financials_without_llm(conn, keyless, fin_env, monkeypatch):
    from tests.fakes import tatasteel_fake

    fake = tatasteel_fake()
    monkeypatch.setattr(refresh_mod, "NSEClient", lambda: _Closing(fake))
    summary = refresh(conn, use_llm=False)
    assert summary["financials"]["fetched"] == 3
    assert summary["enrich"] == {} and "people" not in summary["enrich"]
    failed = summary["financials"]["failed"]
    assert "TATASTEEL" not in failed
    assert all(e.startswith("financials: ") for e in summary["errors"])
    assert len(summary["errors"]) == len(failed) == 17


def test_refresh_records_financials_failure_in_errors(conn, keyless, fin_env, monkeypatch):
    from tests.fakes import FakeNSE

    monkeypatch.setattr(refresh_mod, "NSEClient", lambda: _Closing(FakeNSE({}, {})))
    summary = refresh(conn, use_llm=False)
    assert summary["financials"]["fetched"] == 0
    assert "financials: TATASTEEL: NSEUnavailable: no rows for TATASTEEL" in summary["errors"]


def test_financials_stage_crash_is_reported_not_raised(conn, keyless, fin_env, monkeypatch):
    def crash(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(refresh_mod, "ingest_financials", crash)
    summary = refresh(conn, use_llm=False)
    assert "financials: RuntimeError: boom" in summary["errors"]
    assert summary["price_bars"] == 18


def test_llm_stages_run_with_router_and_report_failures(conn, keyless, fin_env, monkeypatch):
    from tests.fakes import FakeNSE

    monkeypatch.setattr(refresh_mod, "NSEClient", lambda: _Closing(FakeNSE({}, {})))
    monkeypatch.setattr(refresh_mod, "_router", lambda conn, use_llm: _StubRouter())
    monkeypatch.setattr(
        refresh_mod,
        "enrich_people",
        lambda *a, **k: EnrichResult(done=1, empty=2, failed={"s1": "bad"}),
    )
    seen = {}

    def briefs(conn, client, router, since, subscribed):
        seen["subscribed"] = subscribed
        return EnrichResult(done=3, failed={"s2": "worse"})

    monkeypatch.setattr(refresh_mod, "enrich_briefs", briefs)
    monkeypatch.setattr(refresh_mod, "classify_pending", lambda c, r: {})
    summary = refresh(conn, use_llm=True)
    assert summary["enrich"]["people"] == {"done": 1, "empty": 2, "failed": {"s1": "bad"}}
    assert summary["enrich"]["briefs"]["done"] == 3
    assert "people: s1: bad" in summary["errors"] and "briefs: s2: worse" in summary["errors"]
    assert "results" in seen["subscribed"]


class _StubRouter:
    def stats(self):
        return {"calls": 0}


class _Closing:
    """Delegates to a FakeNSE and tolerates close()."""

    def __init__(self, fake):
        self._f = fake

    def __getattr__(self, name):
        return getattr(self._f, name)

    def close(self):
        pass
