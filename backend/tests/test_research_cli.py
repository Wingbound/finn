from datetime import datetime, timedelta

import pytest

from finn import db
from finn.models import IST, Dossier
from scripts import research as cli


def dossier(notes=(), age_min=0.0) -> Dossier:
    return Dossier(
        symbol="ABC", name="Abc Ltd", basis="consolidated",
        built_at=datetime.now(IST) - timedelta(minutes=age_min), sources=[], ledger=None,
        snapshot=None, trajectory=None, health=None, bull=[], bear=[], notes=list(notes),
        cost={"calls": 1, "usd_list_price": 0.0}, build_seconds=1.0,
    )  # fmt: skip


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LLMRouter", lambda conn, settings: object())
    return tmp_path / "cli.sqlite"


def stored(path):
    c = db.connect(path)
    try:
        return db.get_dossier(c, "ABC")
    finally:
        c.close()


def test_cli_saves_a_complete_build(store, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_dossier", lambda *a, **k: dossier())
    assert cli.main(["abc", "--out", str(store)]) == 0
    assert stored(store) is not None
    assert "ABC: 0 ledger rows" in capsys.readouterr().out


def test_cli_does_not_overwrite_with_a_degraded_build(store, monkeypatch, capsys):
    c = db.connect(store)
    db.init_db(c)
    db.save_dossier(c, dossier(age_min=60))
    c.close()
    bad = dossier(["Snapshot unavailable (model unavailable)"])
    monkeypatch.setattr(cli, "build_dossier", lambda *a, **k: bad)
    assert cli.main(["ABC", "--out", str(store)]) == 0
    assert stored(store).notes == []
    out = capsys.readouterr().out
    assert "ABC: warning: rebuild incomplete" in out and "kept the stored dossier" in out


def test_cli_saves_a_degraded_first_build(store, monkeypatch):
    bad = dossier(["Snapshot unavailable (model unavailable)"])
    monkeypatch.setattr(cli, "build_dossier", lambda *a, **k: bad)
    assert cli.main(["ABC", "--out", str(store)]) == 0
    assert stored(store).notes == bad.notes
