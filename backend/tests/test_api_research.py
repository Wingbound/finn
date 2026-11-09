import json
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from finn import db
from finn.api import main as api_main
from finn.api.deps import get_conn
from finn.ingest.screener import ScreenerError
from finn.models import (
    IST,
    Citation,
    Dossier,
    Ledger,
    LedgerRow,
    Point,
    Promise,
    Snapshot,
    Source,
)


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
    assert ev[2][1]["excerpts"] == {"T1": {"2": "page two"}}
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


def test_degraded_rebuild_keeps_stored_dossier(env, monkeypatch):
    client, path = env
    old = dossier(age_min=30)
    save(path, old)
    bad = dossier().model_copy(update={"notes": ["Snapshot unavailable (model unavailable)"]})
    monkeypatch.setattr(api_main, "build_dossier", lambda conn, s, r, **k: bad)
    ev = events(client.get("/research/ABC/build").text)
    msg = "Live rebuild was incomplete; showing the last complete dossier"
    assert ev[-2] == ("progress", {"msg": msg})
    assert ev[-1][0] == "done" and ev[-1][1]["notes"] == []
    assert ev[-1][1]["built_at"] == old.built_at.isoformat()
    c = db.connect(path)
    assert db.get_dossier(c, "ABC").notes == []
    c.close()


def test_degraded_first_build_is_saved(env, monkeypatch):
    client, path = env
    bad = dossier().model_copy(update={"notes": ["Snapshot unavailable (model unavailable)"]})
    monkeypatch.setattr(api_main, "build_dossier", lambda conn, s, r, **k: bad)
    ev = events(client.get("/research/ABC/build").text)
    assert ev[-1][0] == "done" and ev[-1][1]["notes"] == bad.notes
    c = db.connect(path)
    assert db.get_dossier(c, "ABC").notes == bad.notes
    c.close()


class ScriptedQueue:
    """queue.Queue stand-in: EMPTY entries time out (advancing the fake clock)."""

    EMPTY = object()

    def __init__(self, script, clock):
        self.script, self.clock, self.timeouts = list(script), clock, []

    def get(self, timeout=None):
        self.timeouts.append(timeout)
        item = self.script.pop(0) if self.script else self.EMPTY
        if item is self.EMPTY:
            self.clock["t"] += timeout
            raise api_main.queue.Empty
        return item


def test_stream_pings_while_waiting():
    clock = {"t": 0.0}
    q = ScriptedQueue([ScriptedQueue.EMPTY, ("progress", {"msg": "x"}), api_main._DONE], clock)
    out = list(api_main._stream(q, clock=lambda: clock["t"]))
    assert out == [": ping\n\n", 'event: progress\ndata: {"msg": "x"}\n\n']
    assert q.timeouts[0] == 15


def test_stream_times_out_at_285s():
    clock = {"t": 0.0}
    q = ScriptedQueue([], clock)
    out = list(api_main._stream(q, clock=lambda: clock["t"]))
    assert out[-1] == 'event: error\ndata: {"detail": "build timed out"}\n\n'
    assert set(out[:-1]) == {": ping\n\n"} and len(out) == 19
    assert clock["t"] == 285 and max(q.timeouts) <= 15


FACTS_CITE = Citation(source_id="FACTS", page=0, quote="Debt to equity: 1")


def test_done_payload_has_excerpts_for_every_cited_page(env, monkeypatch):
    client, _ = env
    src = Source(id="T1", kind="transcript", title="Q2 call", quarter="Q2 FY27", url="u", pages=["p1", "p2", "p3", "p4"])  # fmt: skip
    t2 = Source(id="T2", kind="transcript", title="Q1 call", quarter="Q1 FY27", url="u", pages=["q1", "q2"])  # fmt: skip
    promise = Promise(id="T2-1", citation=Citation(source_id="T2", page=2, quote="a b c d e f"), topic="t", kind="qualitative", made_in="Q1 FY27")  # fmt: skip
    row = LedgerRow(promise=promise, status="kept", method="judged", evidence=Citation(source_id="T1", page=3, quote="a b c d e f"), rationale="r")  # fmt: skip
    d = dossier().model_copy(
        update={
            "sources": [src, t2],
            "ledger": Ledger(rows=[row], counts={"kept": 1}, credibility_pct=None),
            "bull": [Point(text="b", citation=Citation(source_id="T1", page=4, quote="x"))],
            "bear": [Point(text="f", citation=FACTS_CITE)],
        }
    )
    monkeypatch.setattr(api_main, "build_dossier", lambda conn, s, r, **k: d)
    done = events(client.get("/research/ABC/build").text)[-1][1]
    assert done["excerpts"] == {"T1": {"2": "p2", "3": "p3", "4": "p4"}, "T2": {"2": "q2"}}


def test_cached_done_has_excerpts(env, monkeypatch):
    client, path = env
    save(path, dossier(age_min=3))
    ev = events(client.get("/research/ABC/build").text)
    assert ev[-1][1]["excerpts"] == {"T1": {"2": "page two"}}


def test_save_failure_still_streams_done(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(api_main, "build_dossier", lambda conn, s, r, **k: dossier(s))

    def broken(conn, d):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(api_main.db, "save_dossier", broken)
    ev = events(client.get("/research/ABC/build").text)
    assert [e for e, _ in ev] == ["done"] and ev[0][1]["symbol"] == "ABC"


def test_worker_puts_done_marker_even_if_close_raises(monkeypatch):
    class Conn:
        def close(self):
            raise RuntimeError("close failed")

    fake_db = SimpleNamespace(
        connect=lambda path: Conn(), init_db=lambda c: None, get_dossier=lambda c, s: None,
        save_dossier=lambda c, d: None,
    )  # fmt: skip
    monkeypatch.setattr(api_main, "db", fake_db)
    monkeypatch.setattr(api_main, "get_settings", lambda: SimpleNamespace(db_path="x"))
    monkeypatch.setattr(api_main, "LLMRouter", lambda conn, settings: object())
    monkeypatch.setattr(api_main, "build_dossier", lambda conn, s, r, **k: dossier(s))
    q = api_main.queue.Queue()
    with pytest.raises(RuntimeError):
        api_main._build_worker("ABC", q)
    items = [q.get_nowait() for _ in range(q.qsize())]
    assert items[0][0] == "done" and items[-1] is api_main._DONE


def test_list_carries_the_ledger_status_tally(env):
    client, path = env
    from finn.models import Ledger

    d = dossier().model_copy(
        update={"ledger": Ledger(rows=[], counts={"kept": 1, "pending": 2}, credibility_pct=None)}
    )
    save(path, d)
    assert client.get("/research").json()[0]["counts"]["ledger"] == {"kept": 1, "pending": 2}
    save(path, dossier())  # no ledger at all
    assert client.get("/research").json()[0]["counts"]["ledger"] == {}


# ---- abuse limits on the public build endpoint (Plan 5 final review I1) ----


def test_non_symbols_are_rejected_before_any_work(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(api_main, "build_dossier", lambda *a, **k: pytest.fail("must not build"))
    for path in (
        "/research/TCS%3FX%3D1/build",
        "/research/TCS%3FX%3D1",
        "/research/a%20b/source/T1/1",
    ):
        r = client.get(path)
        assert r.status_code == 400, path
        assert r.json()["detail"] == "Not an NSE symbol"
    assert client.get("/research/M%26M").status_code == 404  # a real symbol shape is fine


def test_a_second_build_of_the_same_symbol_is_refused_while_one_runs(env, monkeypatch):
    import threading
    import time

    client, _ = env
    release = threading.Event()

    def slow(conn, symbol, router, *, progress, **kw):
        release.wait(5)
        return dossier(symbol)

    monkeypatch.setattr(api_main, "build_dossier", slow)
    first = threading.Thread(target=lambda: client.get("/research/ABC/build"))
    first.start()
    for _ in range(100):
        if "ABC" in api_main._inflight:
            break
        time.sleep(0.02)
    ev = events(client.get("/research/ABC/build").text)
    release.set()
    first.join(5)
    assert ev[-1][0] == "error" and "already" in ev[-1][1]["detail"]


def test_builds_stop_at_the_hourly_cap(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(api_main, "MAX_BUILDS_PER_HOUR", 1)
    monkeypatch.setattr(api_main, "build_dossier", lambda conn, s, r, **k: dossier(s))
    assert events(client.get("/research/ABC/build").text)[-1][0] == "done"
    ev = events(client.get("/research/XYZ/build").text)
    assert ev[-1][0] == "error" and "hourly" in ev[-1][1]["detail"]


def test_api_docs_are_hidden_on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    assert api_main.doc_urls() == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    monkeypatch.delenv("VERCEL")
    assert api_main.doc_urls() == {}
