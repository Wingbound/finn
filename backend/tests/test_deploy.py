"""Plan 5 Task 1: what serving from Vercel needs (cold starts, /tmp, CORS, secrets, imports)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

import finn.api.main as main_mod
import scripts.refresh as refresh_mod
from finn import db
from finn.config import Settings, get_settings

SEED = Path(__file__).resolve().parent.parent / "seed" / "finn.sqlite"


def _settings_env(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "cold" / "finn.sqlite"
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("SEED_PATH", str(SEED))
    get_settings.cache_clear()
    return path


def test_get_conn_seeds_without_lifespan(monkeypatch, tmp_path):
    path = _settings_env(monkeypatch, tmp_path)
    try:
        client = TestClient(
            main_mod.app
        )  # no `with`: the lifespan never runs, as on a cold function
        holdings = client.get("/portfolio").json()["holdings"]
        assert len(holdings) == 18 and any(h["close"] for h in holdings)
        assert client.post("/digest", json={"hours": 24 * 366}).json()["counts"]["filings"] > 0
        assert client.get("/health").json()["seeded"] is True
        assert path.exists()
    finally:
        get_settings.cache_clear()


def test_seed_copy_runs_once_under_concurrency(monkeypatch, tmp_path):
    from finn.api import deps

    path = _settings_env(monkeypatch, tmp_path)
    calls = []
    real_copy = shutil.copyfile

    def slow_copy(src, dst):
        calls.append(dst)
        time.sleep(0.05)  # widen the race window
        return real_copy(src, dst)

    monkeypatch.setattr(shutil, "copyfile", slow_copy)
    try:
        settings = get_settings()
        threads = [threading.Thread(target=deps.ensure_seeded, args=(settings,)) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(calls) == 1
        assert db.connect(path).execute("SELECT COUNT(*) FROM filings").fetchone()[0] > 0
    finally:
        get_settings.cache_clear()


def test_vercel_defaults_to_tmp(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    assert Settings(_env_file=None).db_path == Path("/tmp/finn/finn.sqlite")
    monkeypatch.setenv("DB_PATH", "/elsewhere/x.sqlite")
    assert Settings(_env_file=None).db_path == Path("/elsewhere/x.sqlite")


def test_local_default_is_unchanged(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    assert Settings(_env_file=None).db_path == Path("data/finn.sqlite")


def test_allowed_origins_from_csv_env(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://finn.vercel.app, http://localhost:3000")
    assert Settings(_env_file=None).allowed_origins == [
        "https://finn.vercel.app",
        "http://localhost:3000",
    ]
    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://a.example"]')
    assert Settings(_env_file=None).allowed_origins == ["https://a.example"]


def test_health_reports_cors(monkeypatch, tmp_path):
    _settings_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://finn.vercel.app")
    get_settings.cache_clear()
    try:
        assert TestClient(main_mod.app).get("/health").json()["cors"] == ["https://finn.vercel.app"]
    finally:
        get_settings.cache_clear()


def test_keys_are_secret():
    s = Settings(_env_file=None, gemini_api_key="x-secret-1", groq_api_key="x-secret-2")
    assert "x-secret" not in repr(s) and "x-secret" not in str(s.model_dump())
    assert s.api_key("gemini_api_key") == "x-secret-1"
    assert s.api_key("groq_api_key") == "x-secret-2"
    assert Settings(_env_file=None, gemini_api_key="").api_key("gemini_api_key") == ""


@respx.mock
def test_router_still_sends_the_key(tmp_path):
    from finn.llm import LLMRouter

    route = respx.post(url__regex=r"https://api\.groq\.com/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
    )
    conn = db.connect(tmp_path / "r.sqlite")
    db.init_db(conn)
    s = Settings(_env_file=None, groq_api_key="k-groq", gemini_api_key="")
    LLMRouter(conn, s).complete_json("classify", "sys", "usr")
    assert route.calls[0].request.headers["authorization"] == "Bearer k-groq"


def test_api_import_skips_pandas():
    code = "import sys, finn.api.main; print('pandas' in sys.modules or 'yfinance' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        check=True,
    )
    assert out.stdout.strip() == "False"


def test_refresh_exit_2_leaves_the_snapshot_untouched(tmp_path, monkeypatch):
    out = tmp_path / "seed" / "finn.sqlite"
    out.parent.mkdir()
    out.write_bytes(SEED.read_bytes())
    before = out.read_bytes()
    settings = Settings(_env_file=None, gemini_api_key="", groq_api_key="")
    monkeypatch.setattr(refresh_mod, "get_settings", lambda: settings)

    def nse_down(*a, **k):
        raise ConnectionError("nse refused")

    def yahoo_down(*a, **k):
        raise ConnectionError("yahoo refused")

    monkeypatch.setattr(refresh_mod, "ingest_filings", nse_down)
    monkeypatch.setattr(refresh_mod, "fetch_eod", yahoo_down)
    assert refresh_mod.main(["--days", "3", "--no-llm", "--out", str(out)]) == 2
    assert out.read_bytes() == before
    assert sorted(p.name for p in out.parent.iterdir()) == ["finn.sqlite"]  # no temp files left


def test_refresh_partial_failure_is_exit_1_and_writes(tmp_path, monkeypatch):
    from finn.models import PriceBar
    from finn.portfolio import load_portfolio

    out = tmp_path / "seed" / "finn.sqlite"
    out.parent.mkdir()
    out.write_bytes(SEED.read_bytes())
    settings = Settings(_env_file=None, gemini_api_key="", groq_api_key="")
    monkeypatch.setattr(refresh_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(
        refresh_mod, "ingest_filings", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("nse"))
    )
    from datetime import date

    monkeypatch.setattr(
        refresh_mod,
        "fetch_eod",
        lambda holdings, **_: [
            PriceBar(
                symbol=h.symbol, date=date(2026, 11, 10), open=1, high=1, low=1, close=1, volume=1
            )
            for h in load_portfolio()
        ],
    )
    assert refresh_mod.main(["--days", "3", "--no-llm", "--out", str(out)]) == 1
    c = db.connect(out)
    assert c.execute("SELECT COUNT(*) FROM prices WHERE date = '2026-11-10'").fetchone()[0] == 18
    c.close()
