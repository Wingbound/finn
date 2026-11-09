import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from finn import db
from finn.api import main as api_main
from finn.api.deps import get_conn
from finn.ingest.screener import ScreenerError
from finn.models import IST, Citation, Dossier, Point, Snapshot, Source


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "api.sqlite"
    c = db.connect(path)
    db.init_db(c)
    c.close()

    def _conn():
        cc = db.connect(path)
        try:
            yield cc
        finally:
            cc.close()

    api_main.app.dependency_overrides[get_conn] = _conn
    monkeypatch.setattr(api_main, "get_settings", lambda: type("S", (), {"db_path": path})())
    monkeypatch.setattr(api_main, "LLMRouter", lambda conn, settings: object())
    yield TestClient(api_main.app), path
    api_main.app.dependency_overrides.clear()


def dossier(symbol="ABC", age_min=0.0) -> Dossier:
    cit = Citation(source_id="T1", page=2, quote="a b c d e f")
    return Dossier(
        symbol=symbol, name="Abc Ltd", basis="consolidated",
        built_at=datetime.now(IST) - timedelta(minutes=age_min),
        sources=[Source(id="T1", kind="transcript", title="Q2 call", quarter="Q2 FY27",
                        url="http://x", pages=["page one", "page two"])],
        ledger=None, snapshot=Snapshot(summary=[Point(text="t", citation=cit)]),
        trajectory=None, health=None, bull=[], bear=[], notes=[], cost={"calls": 1},
        build_seconds=1.0,
    )  # fmt: skip


def save(path, d):
    c = db.connect(path)
    db.save_dossier(c, d)
    c.close()


def events(text):
    out = []
    for block in text.strip().split("\n\n"):
        ev, data = block.split("\n")
        out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_list_and_get(env):
    client, path = env
    assert client.get("/research").json() == []
    r = client.get("/research/abc")
    assert r.status_code == 404
    assert r.json() == {"detail": "not built", "build": "/research/ABC/build"}
    save(path, dossier())
    row = client.get("/research").json()[0]
    assert row["symbol"] == "ABC" and row["name"] == "Abc Ltd" and "counts" in row
    body = client.get("/research/abc").json()
    assert body["symbol"] == "ABC" and "pages" not in body["sources"][0]


def test_source_page(env):
    client, path = env
    save(path, dossier())
    r = client.get("/research/ABC/source/T1/2")
    assert r.status_code == 200
    assert r.json() == {"title": "Q2 call", "page": 2, "text": "page two"}
    assert client.get("/research/ABC/source/T1/3").status_code == 404
    assert client.get("/research/ABC/source/T9/1").status_code == 404
    assert client.get("/research/ZZZ/source/T1/1").status_code == 404


def test_search_requires_q(env):
    client, _ = env
    assert client.get("/research/search?q=").status_code == 422
    assert client.get("/research/search").status_code == 422


def test_search_proxies(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(api_main.screener, "search", lambda q: [{"name": q}])
    assert client.get("/research/search?q=tata").json() == [{"name": "tata"}]


def test_build_streams_progress_then_done(env, monkeypatch):
    client, path = env

    def fake(conn, symbol, router, *, progress, **kw):
        progress("one")
        progress("two")
        return dossier(symbol)

    monkeypatch.setattr(api_main, "build_dossier", fake)
    r = client.get("/research/abc/build")
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"
    ev = events(r.text)
    assert [e for e, _ in ev] == ["progress", "progress", "done"]
    assert ev[0][1] == {"msg": "one"}
    assert ev[2][1]["symbol"] == "ABC" and "pages" not in ev[2][1]["sources"][0]
    c = db.connect(path)
    assert db.get_dossier(c, "ABC").sources[0].pages == ["page one", "page two"]
    c.close()


def test_build_unknown_symbol_errors(env, monkeypatch):
    client, _ = env

    def fake(*a, **k):
        raise ScreenerError("no screener financial data for NOPE")

    monkeypatch.setattr(api_main, "build_dossier", fake)
    ev = events(client.get("/research/NOPE/build").text)
    assert ev[-1][0] == "error" and "NOPE" in ev[-1][1]["detail"]


def test_build_unexpected_error(env, monkeypatch):
    client, _ = env

    def fake(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api_main, "build_dossier", fake)
    ev = events(client.get("/research/ABC/build").text)
    assert ev[-1][0] == "error"


def test_build_uses_fresh_cache(env, monkeypatch):
    client, path = env
    save(path, dossier(age_min=3))

    def fake(*a, **k):
        raise AssertionError("must not rebuild")

    monkeypatch.setattr(api_main, "build_dossier", fake)
    ev = events(client.get("/research/ABC/build").text)
    assert ev[0] == ("progress", {"msg": "Using cached dossier"})
    assert ev[1][0] == "done" and ev[1][1]["symbol"] == "ABC"


def test_build_rebuilds_stale_cache(env, monkeypatch):
    client, path = env
    save(path, dossier(age_min=30))
    monkeypatch.setattr(api_main, "build_dossier", lambda conn, s, r, **k: dossier(s))
    ev = events(client.get("/research/ABC/build").text)
    assert [e for e, _ in ev] == ["done"]
