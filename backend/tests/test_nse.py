import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from finn import db
from finn.ingest import nse
from finn.ingest.nse import NSEClient, NSEUnavailable, ingest_filings, parse_announcement

FIX = Path(__file__).parent / "fixtures" / "nse"
START, END = date(2026, 10, 8), date(2026, 11, 8)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(nse, "_sleep", lambda s: None)


@pytest.fixture
def reliance():
    return json.loads((FIX / "RELIANCE.json").read_text())


def json_response(data):
    return httpx.Response(200, json=data)


def forbidden():
    return httpx.Response(403, html="<html>Access Denied</html>")


def test_parse_announcement_fields(reliance):
    f = parse_announcement(reliance[0])
    assert f.symbol == "RELIANCE"
    assert f.filed_at.utcoffset() == timedelta(hours=5, minutes=30)
    assert f.pdf_url.startswith("https://nsearchives.nseindia.com/")


def test_parse_handles_missing_pdf_and_summary(reliance):
    raw = {**reliance[0], "attchmntFile": None, "voiceSummary": None}
    f = parse_announcement(raw)
    assert f.pdf_url is None and f.nse_summary is None


@respx.mock
def test_retry_then_success(reliance):
    respx.get("https://www.nseindia.com/").respond(403)
    api = respx.get(nse.API_URL).mock(
        side_effect=[forbidden(), forbidden(), json_response(reliance)]
    )
    out = NSEClient().fetch_announcements("RELIANCE", START, END)
    assert out == reliance
    assert api.call_count == 3


@respx.mock
def test_persistent_403_is_recorded_not_raised(conn):
    respx.get("https://www.nseindia.com/").respond(403)
    respx.get(nse.API_URL).mock(return_value=forbidden())
    result = ingest_filings(conn, NSEClient(), ["RELIANCE"], START, END)
    assert result.added == 0 and list(result.failed) == ["RELIANCE"]
    assert "HTTP 403" in result.failed["RELIANCE"]
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 0
    assert db.get_meta(conn, "filings_as_of") is None


@respx.mock
def test_non_json_content_type_is_failure():
    respx.get("https://www.nseindia.com/").respond(200)
    respx.get(nse.API_URL).mock(return_value=httpx.Response(200, html="<html></html>"))
    with pytest.raises(NSEUnavailable):
        NSEClient().fetch_announcements("RELIANCE", START, END)


@respx.mock
def test_failing_symbol_keeps_the_others_and_holds_as_of(conn, reliance):
    respx.get("https://www.nseindia.com/").respond(403)
    api = respx.get(nse.API_URL).mock(
        side_effect=lambda req: (
            forbidden() if req.url.params["symbol"] == "TRENT" else json_response(reliance)
        )
    )
    result = ingest_filings(conn, NSEClient(), ["TRENT", "RELIANCE"], START, END)
    assert list(result.failed) == ["TRENT"]
    assert api.call_count == 3 + 1  # TRENT exhausts its retries, RELIANCE still runs
    stored = conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
    assert result.added == stored == len({r["seq_id"] for r in reliance})
    assert db.get_meta(conn, "filings_as_of") is None  # not every symbol is fresh


@respx.mock
def test_malformed_rows_are_skipped_and_counted(conn, reliance):
    bad = [
        {k: v for k, v in reliance[0].items() if k != "an_dt"},  # missing an_dt
        {**reliance[0], "seq_id": "bad-date", "an_dt": "yesterday"},  # invalid an_dt
        {**reliance[0], "seq_id": "bad-type", "an_dt": 20261108},
        {"seq_id": "only-id"},  # missing keys
        "not a row",
    ]
    respx.get("https://www.nseindia.com/").respond(403)
    respx.get(nse.API_URL).mock(return_value=json_response(reliance + bad))
    result = ingest_filings(conn, NSEClient(), ["RELIANCE"], START, END)
    assert result.skipped == len(bad) and result.failed == {}
    assert result.added == len({r["seq_id"] for r in reliance})
    assert db.get_meta(conn, "filings_as_of") is not None


@respx.mock
def test_polite_pause_between_symbols(conn, monkeypatch):
    sleeps = []
    monkeypatch.setattr(nse, "_sleep", sleeps.append)
    respx.get("https://www.nseindia.com/").respond(403)
    respx.get(nse.API_URL).mock(return_value=json_response([]))
    ingest_filings(conn, NSEClient(), ["RELIANCE", "TRENT", "M&M"], START, END)
    assert sleeps == [nse.SYMBOL_PAUSE_S] * 2 and nse.SYMBOL_PAUSE_S == 0.5


@respx.mock
def test_symbol_with_ampersand_encoded():
    respx.get("https://www.nseindia.com/").respond(403)
    api = respx.get(nse.API_URL).mock(return_value=json_response([]))
    NSEClient().fetch_announcements("M&M", START, END)
    url = str(api.calls.last.request.url)
    assert "symbol=M%26M" in url
    assert "from_date=08-10-2026" in url and "to_date=08-11-2026" in url


@respx.mock
def test_ingest_counts_new_only(conn, reliance):
    respx.get("https://www.nseindia.com/").respond(403)
    respx.get(nse.API_URL).mock(return_value=json_response(reliance))
    first = ingest_filings(conn, NSEClient(), ["RELIANCE"], START, END)
    assert first.added == len({r["seq_id"] for r in reliance})
    assert ingest_filings(conn, NSEClient(), ["RELIANCE"], START, END).added == 0
    assert db.get_meta(conn, "filings_as_of") is not None


@respx.mock
def test_fetch_integrated_financials_returns_data_list():
    route = respx.get(nse.INTEGRATED_URL).mock(
        return_value=json_response({"data": [{"symbol": "TATASTEEL"}], "totalCount": 1})
    )
    respx.get("https://www.nseindia.com/").respond(200)
    out = NSEClient().fetch_integrated_financials("TATASTEEL")
    assert out == [{"symbol": "TATASTEEL"}]
    params = route.calls[0].request.url.params
    assert params["symbol"] == "TATASTEEL"
    assert params["type"] == "Integrated Filing- Financials"


@respx.mock
def test_fetch_integrated_financials_rejects_non_object():
    respx.get("https://www.nseindia.com/").respond(200)
    respx.get(nse.INTEGRATED_URL).mock(return_value=json_response([{"a": 1}]))
    with pytest.raises(NSEUnavailable):
        NSEClient().fetch_integrated_financials("TATASTEEL")


@respx.mock
def test_fetch_bytes_rejects_oversize():
    respx.get("https://www.nseindia.com/").respond(200)
    respx.get("https://nsearchives.nseindia.com/x.xml").respond(
        200, content=b"abc", headers={"content-length": "30000000"}
    )
    with pytest.raises(NSEUnavailable, match="exceeds"):
        NSEClient().fetch_bytes("https://nsearchives.nseindia.com/x.xml", max_bytes=25_000_000)


@respx.mock
def test_fetch_bytes_ok():
    respx.get("https://www.nseindia.com/").respond(200)
    respx.get("https://nsearchives.nseindia.com/x.xml").respond(200, content=b"<a/>")
    assert NSEClient().fetch_bytes("https://nsearchives.nseindia.com/x.xml") == b"<a/>"
