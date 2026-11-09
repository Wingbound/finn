import json

import pytest

from finn import db
from finn.research.pipeline import build_dossier
from scripts import eval_research
from tests.fakes import FakeRouter
from tests.test_research_pipeline import (
    FailingDocs,
    FakeScreener,
    reply,
    seeded,  # noqa: F401  (fixture)
)


def facts_reply(task, system, user):
    """Like `reply`, but bull cites the first computed line of the FACTS block."""
    out = reply(task, system, user)
    if task == "reason" and "FACTS" in user:
        line = next(ln for ln in user.splitlines() if ln.startswith("Revenue CAGR"))
        out["bull"].append({"text": line, "quote": line, "source_id": "FACTS", "page": 0})
    return out


@pytest.fixture
def stored(seeded):  # noqa: F811
    d = build_dossier(
        seeded, "PERSISTENT", FakeRouter(facts_reply), screener_client=FakeScreener(),
        doc_client=FailingDocs(),
    )  # fmt: skip
    db.save_dossier(seeded, d)
    return seeded


def test_guard_recorded_on_dossier(stored):
    d = db.get_dossier(stored, "PERSISTENT")
    assert set(d.guard) == {
        "promises_proposed", "promises_kept", "points_proposed", "points_kept"
    }  # fmt: skip
    assert d.guard["promises_proposed"] >= d.guard["promises_kept"] > 0
    assert d.guard["points_proposed"] >= d.guard["points_kept"] > 0


def test_old_payload_has_empty_guard(stored):
    payload = json.loads(db.get_dossier(stored, "PERSISTENT").model_dump_json())
    payload.pop("guard")
    from finn.models import Dossier

    assert Dossier.model_validate(payload).guard == {}


def test_eval_verifies_everything(stored):
    res = eval_research.evaluate(stored)
    assert len(res) == 1
    r = res[0]
    assert r.failures == [] and r.verified == r.total > 0
    assert r.facts >= 1


def test_eval_report_has_columns(stored, capsys):
    path = stored.execute("PRAGMA database_list").fetchone()["file"]
    assert eval_research.main(["--db", path]) == 0
    out = capsys.readouterr().out
    assert "| PERSISTENT |" in out and "| total |" in out.lower()
    assert "100%" in out
    d = db.get_dossier(stored, "PERSISTENT")
    g = d.guard
    assert f"{g['promises_kept']}/{g['promises_proposed']}" in out
    assert f"{g['points_kept']}/{g['points_proposed']}" in out
    assert "| FACTS citations |" in out
    r = eval_research.evaluate(stored)[0]
    row = next(ln for ln in out.splitlines() if ln.startswith("| PERSISTENT |"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    head = [c.strip() for c in out.splitlines()[0].strip("|").split("|")]
    assert cells[head.index("FACTS citations")] == str(r.facts) and r.facts >= 1


def test_corrupt_ledger_quote_is_listed(stored, capsys):
    d = db.get_dossier(stored, "PERSISTENT")
    assert d.ledger and d.ledger.rows
    original = d.ledger.rows[0].promise.citation.quote
    payload = stored.execute("SELECT payload_json FROM dossiers").fetchone()[0]
    stored.execute(
        "UPDATE dossiers SET payload_json = ?",
        (
            payload.replace(
                json.dumps(original)[1:-1], "this quote was never said by anyone here", 1
            ),
        ),
    )
    stored.commit()
    res = eval_research.evaluate(stored)[0]
    assert len(res.failures) >= 1 and res.verified == res.total - len(res.failures)
    assert res.failures[0].startswith("PERSISTENT | ledger")
    path = stored.execute("PRAGMA database_list").fetchone()["file"]
    eval_research.main(["--db", path])
    assert "this quote was never said" in capsys.readouterr().out
