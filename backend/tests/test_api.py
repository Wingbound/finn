import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finn import db
from finn.api import main as api_main
from finn.api.deps import get_conn, get_now
from finn.api.main import SEED_PATH, app, copy_seed_if_missing
from finn.classify.rules import classify_rules
from finn.config import Settings
from finn.ingest.nse import parse_announcement
from finn.models import IST, PriceBar
from finn.portfolio import load_portfolio

FIX = Path(__file__).parent / "fixtures" / "nse"
NOW = datetime(2026, 11, 8, 20, 0, tzinfo=IST)  # Sunday evening


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "api.sqlite"
    seed = db.connect(path)
    db.init_db(seed)
    filings = [parse_announcement(r) for r in json.loads((FIX / "portfolio_month.json").read_text())]
    db.upsert_filings(seed, filings)
    db.save_classifications(
        seed, {f.seq_id: c for f in filings if (c := classify_rules(f)) is not None}
    )
    db.set_meta(seed, "filings_as_of", "2026-11-08T19:00:00+05:30")
    # 30 weekday sessions per holding; the last bar jumps 10% on 5x volume
    days = []
    d = date(2026, 11, 6)
    while len(days) < 30:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    bars = []
    for h in load_portfolio():
        for i, day in enumerate(days):
            last = i == len(days) - 1
            close = 110.0 if last else 100.0
            bars.append(PriceBar(symbol=h.symbol, date=day, open=100, high=close, low=99,
                                 close=close, volume=500 if last else 100))
    db.upsert_prices(seed, bars)
    seed.close()

    def _conn():
        c = db.connect(path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = _conn
    app.dependency_overrides[get_now] = lambda: NOW
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health").json()
    assert r == {"ok": True, "filings_as_of": "2026-11-08T19:00:00+05:30", "prices_as_of": None}


def test_digest_default_24h_window_shape(client):
    r = client.post("/digest", json={"hours": 168})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"window", "as_of", "counts", "stories", "routine", "hidden"}
    assert body["window"]["end"] == NOW.isoformat()
    assert body["window"]["start"] == (NOW - timedelta(hours=168)).isoformat()
    assert body["as_of"] == "2026-11-08T19:00:00+05:30"
    c = body["counts"]
    assert c["shown"] == len(body["stories"])
    assert c["hidden"] == len(body["hidden"])
    assert c["routine"] == sum(len(v) for v in body["routine"].values())
    assert c["filings"] > 0 and c["shown"] > 0
    assert body["stories"][0]["latest_at"].endswith("+05:30")
    # default 24h call also works
    assert client.post("/digest", json={}).status_code == 200


def test_digest_floor_moves_items_between_shown_and_routine(client):
    win = {"start": "2026-10-08T00:00:00+05:30", "end": "2026-11-08T23:59:59+05:30"}
    crit = client.post("/digest", json={**win, "floor": "critical"}).json()["counts"]
    every = client.post("/digest", json={**win, "floor": "everything"}).json()["counts"]
    assert crit["shown"] < every["shown"]
    assert every["routine"] == 0
    assert crit["shown"] + crit["routine"] == every["shown"]
    assert crit["filings"] == every["filings"] and crit["hidden"] == every["hidden"]


def test_digest_empty_window(client):
    r = client.post(
        "/digest", json={"start": "2030-01-05T00:00:00+05:30", "end": "2030-01-06T23:59:59+05:30"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["counts"] == {"shown": 0, "routine": 0, "hidden": 0, "filings": 0}
    assert body["stories"] == [] and body["routine"] == {} and body["hidden"] == []


def test_alerts_accept_custom_rules(client):
    many = client.post("/alerts", json={"price_move_pct": 0.1, "volume_multiple": 1.0}).json()
    none = client.post(
        "/alerts", json={"price_move_pct": 50, "volume_multiple": 50, "categories": []}
    ).json()
    assert len(many["alerts"]) > 18
    assert none["alerts"] == []
    kinds = {a["kind"] for a in many["alerts"]}
    assert {"price", "volume"} <= kinds
    dates = [a["date"] for a in many["alerts"]]
    assert dates == sorted(dates, reverse=True)


def test_portfolio_has_18_rows_with_spark(client):
    body = client.get("/portfolio").json()
    assert len(body["holdings"]) == 18
    h = body["holdings"][0]
    assert len(h["spark"]) == 20
    assert h["close"] == 110.0
    assert h["change_pct"] == 10.0
    assert h["vol_ratio"] == 5.0
    assert h["date"] == "2026-11-06"
    assert set(h) == {
        "symbol", "name", "sector", "size", "date", "close", "change_pct", "vol_ratio", "spark"
    }


def test_portfolio_holding_without_bars_has_nulls(client, tmp_path):
    empty = db.connect(tmp_path / "empty.sqlite")
    db.init_db(empty)
    empty.close()

    def _conn():
        c = sqlite3.connect(tmp_path / "empty.sqlite")
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = _conn
    h = client.get("/portfolio").json()["holdings"][0]
    assert h["close"] is None and h["vol_ratio"] is None and h["spark"] == []
    assert h["date"] is None


def test_filing_detail_and_unknown_404(client):
    digest = client.post(
        "/digest", json={"start": "2026-10-08T00:00:00+05:30", "end": "2026-11-08T23:59:59+05:30"}
    ).json()
    seq = digest["stories"][0]["headline"]["filing"]["seq_id"]
    r = client.get(f"/filings/{seq}")
    assert r.status_code == 200
    assert r.json()["filing"]["seq_id"] == seq
    assert client.get("/filings/does-not-exist").status_code == 404


def test_unknown_filing_404(client):
    assert client.get("/filings/nope").status_code == 404


def test_digest_rejects_bad_windows(client):
    assert client.post("/digest", json={"hours": 1_000_000_000}).status_code == 422
    assert client.post("/digest", json={"hours": 0}).status_code == 422
    inverted = {"start": "2026-11-08T00:00:00+05:30", "end": "2026-11-01T00:00:00+05:30"}
    assert client.post("/digest", json=inverted).status_code == 422
    # start-only after "now" (2026-11-08 20:00 IST) is also rejected
    assert client.post("/digest", json={"start": "2026-11-09T00:00:00+05:30"}).status_code == 422


def test_alerts_reject_out_of_range_rules(client):
    assert client.post("/alerts", json={"lookback": 0}).status_code == 422
    assert client.post("/alerts", json={"price_move_pct": -1}).status_code == 422
    bad = {"overrides": {"TRENT": {"volume_multiple": 0}}}
    assert client.post("/alerts", json=bad).status_code == 422


def test_seed_copied_when_db_missing(tmp_path):
    seed = tmp_path / "seed.sqlite"
    seed.write_bytes(b"seed-bytes")
    target = tmp_path / "data" / "nested" / "finn.sqlite"
    assert copy_seed_if_missing(target, seed) is True
    assert target.read_bytes() == b"seed-bytes"


def test_seed_never_overwrites_existing_db(tmp_path):
    seed = tmp_path / "seed.sqlite"
    seed.write_bytes(b"seed-bytes")
    target = tmp_path / "finn.sqlite"
    target.write_bytes(b"live-data")
    assert copy_seed_if_missing(target, seed) is False
    assert target.read_bytes() == b"live-data"


def test_no_seed_no_copy(tmp_path):
    target = tmp_path / "finn.sqlite"
    assert copy_seed_if_missing(target, tmp_path / "absent.sqlite") is False
    assert not target.exists()


def test_startup_copies_seed_to_settings_db_path(tmp_path, monkeypatch):
    seed = tmp_path / "seed.sqlite"
    seed.write_bytes(b"seed-bytes")
    target = tmp_path / "data" / "finn.sqlite"
    monkeypatch.setattr(api_main, "SEED_PATH", seed)
    monkeypatch.setattr(
        api_main, "get_settings", lambda: Settings(_env_file=None, db_path=target)
    )
    with TestClient(app):
        pass
    assert target.read_bytes() == b"seed-bytes"


def test_committed_seed_path_points_at_backend_seed():
    assert SEED_PATH == Path(__file__).resolve().parent.parent / "seed" / "finn.sqlite"
