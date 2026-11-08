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
def test_persistent_403_raises(conn):
    respx.get("https://www.nseindia.com/").respond(403)
    respx.get(nse.API_URL).mock(return_value=forbidden())
    with pytest.raises(NSEUnavailable):
        ingest_filings(conn, NSEClient(), ["RELIANCE"], START, END)
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 0
    assert db.get_meta(conn, "filings_as_of") is None


@respx.mock
def test_non_json_content_type_is_failure():
    respx.get("https://www.nseindia.com/").respond(200)
    respx.get(nse.API_URL).mock(return_value=httpx.Response(200, html="<html></html>"))
    with pytest.raises(NSEUnavailable):
        NSEClient().fetch_announcements("RELIANCE", START, END)


@respx.mock
def test_failure_on_later_symbol_writes_nothing(conn, reliance):
    respx.get("https://www.nseindia.com/").respond(403)
    respx.get(nse.API_URL).mock(
        side_effect=[json_response(reliance), forbidden(), forbidden(), forbidden()]
    )
    with pytest.raises(NSEUnavailable):
        ingest_filings(conn, NSEClient(), ["RELIANCE", "TRENT"], START, END)
    assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] == 0


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
    assert first == len({r["seq_id"] for r in reliance})
    assert ingest_filings(conn, NSEClient(), ["RELIANCE"], START, END) == 0
    assert db.get_meta(conn, "filings_as_of") is not None
