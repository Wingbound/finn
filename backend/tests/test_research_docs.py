import json
from pathlib import Path

import httpx
import pytest

from finn import db
from finn.ingest.screener import parse_documents
from finn.research import docs
from finn.research.docs import (
    DocClient,
    DocError,
    call_quarter,
    collect_sources,
    get_pages,
    pdf_pages,
)

FX = Path(__file__).parent / "fixtures"
HELLO = (FX / "pdf/hello.pdf").read_bytes()
TRANSCRIPTS = json.loads((FX / "research/PERSISTENT_transcripts.json").read_text())
DOCS = parse_documents((FX / "research/PERSISTENT_screener.html").read_text())


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    return c


class FakeClient:
    def __init__(self, body=HELLO, exc=None):
        self.body, self.exc, self.calls = body, exc, []

    def fetch_bytes(self, url, max_bytes=40_000_000):
        self.calls.append(url)
        if self.exc:
            raise self.exc
        return self.body


def _seed(conn, items):
    for t in items:
        for i, p in enumerate(t["pages"], 1):
            conn.execute("INSERT INTO doc_pages VALUES (?,?,?)", (t["url"], i, p))
    conn.commit()


def test_call_quarter():
    exp = {
        "Jan": "Q3 FY26", "Feb": "Q3 FY26", "Mar": "Q3 FY26", "Apr": "Q4 FY26",
        "May": "Q4 FY26", "Jun": "Q4 FY26", "Jul": "Q1 FY27", "Aug": "Q1 FY27",
        "Sep": "Q1 FY27", "Oct": "Q2 FY27", "Nov": "Q2 FY27", "Dec": "Q2 FY27",
    }  # fmt: skip
    for m, q in exp.items():
        assert call_quarter(f"{m} 2026") == q


def test_pdf_pages():
    pages = pdf_pages(HELLO)
    assert len(pages) == 1 and "Ramesh Iyer" in pages[0]
    assert pdf_pages(b"garbage") == []
    assert pdf_pages(HELLO, max_pages=0) == []


def test_get_pages_caches(conn):
    c = FakeClient()
    assert len(get_pages(conn, c, "u")) == 1
    assert len(get_pages(conn, c, "u")) == 1
    assert len(c.calls) == 1


def test_get_pages_empty_sentinel(conn):
    c = FakeClient(body=b"garbage")
    assert get_pages(conn, c, "u") == []
    assert get_pages(conn, c, "u") == []
    assert len(c.calls) == 1


def test_get_pages_error_not_cached(conn):
    c = FakeClient(exc=DocError("x"))
    with pytest.raises(DocError):
        get_pages(conn, c, "u")
    assert conn.execute("SELECT COUNT(*) FROM doc_pages").fetchone()[0] == 0


def test_collect_sources(conn):
    _seed(conn, TRANSCRIPTS)
    msgs = []
    c = FakeClient(exc=DocError("boom"))
    sources, notes = collect_sources(conn, c, DOCS, progress=msgs.append)
    assert [s.id for s in sources] == ["T1", "T2", "T3", "T4"]
    t1 = sources[0]
    assert t1.title == "Q2 FY27 earnings call (Oct 2026)"
    assert t1.quarter == "Q2 FY27" and t1.kind == "transcript"
    assert len(t1.pages) == len(TRANSCRIPTS[0]["pages"])
    assert any("annual report" in n.lower() for n in notes)
    assert not any(s.kind == "annual_report" for s in sources)
    assert msgs[0] == f"Reading {t1.title}"
    assert "Reading Annual Report 2026" in msgs


def test_collect_sources_ar_ok(conn):
    _seed(conn, TRANSCRIPTS)
    sources, notes = collect_sources(conn, FakeClient(), DOCS)
    ar = sources[-1]
    assert ar.id == "AR" and ar.title == "Annual Report 2026" and ar.quarter is None
    assert notes == []


def test_collect_sources_missing_transcripts(conn):
    _seed(conn, TRANSCRIPTS[:2])
    c = FakeClient(exc=DocError("404"))
    sources, notes = collect_sources(conn, c, DOCS)
    assert [s.id for s in sources] == ["T1", "T2"]
    assert any("Apr 2026 transcript unavailable" in n for n in notes)


def test_collect_sources_skips_unposted(conn):
    d = {
        "annual_reports": [],
        "concalls": [{"date": "Nov 2026", "transcript_url": None, "ppt_url": None}],
    }
    c = FakeClient()
    assert collect_sources(conn, c, d) == ([], [])
    assert c.calls == []


def test_collect_sources_empty_text_skipped(conn):
    d = {
        "annual_reports": [],
        "concalls": [{"date": "Oct 2026", "transcript_url": "u", "ppt_url": None}],
    }
    sources, notes = collect_sources(conn, FakeClient(body=b"junk"), d)
    assert sources == [] and "Oct 2026 transcript unavailable" in notes[0]


def _client(handler):
    return DocClient(transport=httpx.MockTransport(handler))


def test_docclient_headers_and_retry(monkeypatch):
    monkeypatch.setattr(docs, "_sleep", lambda s: None)
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(500) if len(seen) < 3 else httpx.Response(200, content=b"%PDF-1")

    with _client(h) as c:
        assert c.fetch_bytes("https://www.bseindia.com/x.pdf") == b"%PDF-1"
    assert len(seen) == 3
    assert seen[0].headers["referer"] == "https://www.bseindia.com/"
    assert "Mozilla" in seen[0].headers["user-agent"]


def test_docclient_no_referer_elsewhere():
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(200, content=b"%PDF-1")

    _client(h).fetch_bytes("https://www.persistent.com/a.pdf")
    assert "referer" not in seen[0].headers


def test_docclient_errors(monkeypatch):
    monkeypatch.setattr(docs, "_sleep", lambda s: None)
    with pytest.raises(DocError):
        _client(lambda r: httpx.Response(404)).fetch_bytes("https://a/x")
    with pytest.raises(DocError):
        _client(lambda r: httpx.Response(200, content=b"<html>")).fetch_bytes("https://a/x")
    with pytest.raises(DocError):
        _client(lambda r: httpx.Response(200, content=b"%PDF" + b"0" * 100)).fetch_bytes(
            "https://a/x", max_bytes=50
        )

    def boom(req):
        raise httpx.ConnectError("no")

    with pytest.raises(DocError):
        _client(boom).fetch_bytes("https://a/x")
