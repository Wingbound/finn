import itertools
import json
from types import SimpleNamespace

import pytest

from finn import db
from finn.ingest.screener import ScreenerError
from finn.models import Dossier, public
from finn.research.docs import DocError
from finn.research.pipeline import build_dossier
from tests.fakes import FIXTURES, FakeRouter

HTML = (FIXTURES / "research" / "PERSISTENT_screener.html").read_text()
TRANSCRIPTS = json.loads((FIXTURES / "research" / "PERSISTENT_transcripts.json").read_text())
REAL_A = "Q2 FY27 revenue stood at USD 487.6 million, registering a year-on-year growth of 20%."
REAL_B = (
    "In terms of financing, we intend replacing the Euro 1.4 billion 18-month bridge loan "
    "with longer tenure, capital and favorable terms."
)


class FakeScreener:
    def __init__(self, status=200):
        self.status = status

    def get(self, url):
        return SimpleNamespace(status_code=self.status, text=HTML)


class FailingDocs:
    def fetch_bytes(self, url, max_bytes=40_000_000):
        raise DocError("offline")


def reply(task, system, user):
    if task == "extract_transcript":
        return {
            "promises": [
                {
                    "quote": REAL_B,
                    "page": 1,
                    "topic": "financing bridge loan",
                    "kind": "qualitative",
                }
            ]
        }
    if task == "reason":
        pt = {"text": "Revenue grew twenty percent.", "quote": REAL_A, "source_id": "T1", "page": 8}
        if "FACTS" in user:
            return {"bull": [pt], "bear": []}
        return {"summary": [pt]}
    return {"judgements": []}


@pytest.fixture
def seeded(conn):
    for t in TRANSCRIPTS:
        db.save_doc_pages(conn, t["url"], t["pages"])
    return conn


def test_build_end_to_end(seeded):
    msgs: list[str] = []
    router = FakeRouter(reply)
    d = build_dossier(
        seeded, "persistent", router, screener_client=FakeScreener(), doc_client=FailingDocs(),
        progress=msgs.append,
    )  # fmt: skip
    assert d.symbol == "PERSISTENT" and d.basis == "consolidated" and d.name
    assert len(d.sources) == 4
    assert d.ledger is not None and d.ledger.rows
    assert d.trajectory is not None and d.health is not None
    assert d.snapshot is not None and d.bull
    assert any("nnual" in n for n in d.notes)
    assert set(d.cost) >= {"calls", "cached", "input_tokens", "output_tokens", "usd_list_price"}
    assert msgs[0] == "Resolving PERSISTENT on screener"
    assert msgs[1] == (
        "Found 34 transcripts (reading the latest 4) and 15 annual report(s) (reading the latest)"
    )
    order = [
        m for m in msgs if m.startswith(("Reading", "Extracting", "Checking", "Writing", "Done"))
    ]
    kinds = [m.split()[0] for m in order]
    assert kinds[0] == "Reading"
    assert kinds.index("Extracting") > kinds.index("Reading")
    assert kinds.index("Checking") > max(i for i, k in enumerate(kinds) if k == "Extracting")
    assert kinds[-2:] == ["Writing", "Done"]
    assert msgs[-1].startswith("Done in ")
    assert "pages" in d.sources[0].model_dump()
    assert "pages" not in public(d)["sources"][0]


def test_deadline_skips_llm_sections(seeded):
    clock = itertools.count(0, 10)
    router = FakeRouter(reply)
    d = build_dossier(
        seeded, "PERSISTENT", router, screener_client=FakeScreener(), doc_client=FailingDocs(),
        deadline_s=0, now=lambda: float(next(clock)),
    )  # fmt: skip
    assert router.calls == []
    assert d.trajectory is not None and d.health is not None
    assert d.ledger is None and d.snapshot is None and d.bull == [] and d.bear == []
    assert any("snapshot skipped: build deadline reached" in n for n in d.notes)
    assert any("ledger skipped: build deadline reached" in n for n in d.notes)


def test_stage_failure_becomes_note(seeded, monkeypatch):
    def boom(*a, **k):
        raise ValueError("x")

    monkeypatch.setattr("finn.research.pipeline.snapshot", boom)
    d = build_dossier(
        seeded, "PERSISTENT", FakeRouter(reply), screener_client=FakeScreener(),
        doc_client=FailingDocs(),
    )  # fmt: skip
    assert "snapshot failed: ValueError" in d.notes
    assert d.ledger is not None


def test_unknown_symbol_propagates(conn):
    with pytest.raises(ScreenerError):
        build_dossier(conn, "NOPE", FakeRouter({}), screener_client=FakeScreener(404))


def test_dossier_roundtrip_keeps_pages(seeded):
    d = build_dossier(
        seeded, "PERSISTENT", FakeRouter(reply), screener_client=FakeScreener(),
        doc_client=FailingDocs(),
    )  # fmt: skip
    db.save_dossier(seeded, d)
    got = db.get_dossier(seeded, "PERSISTENT")
    assert isinstance(got, Dossier) and got.sources[0].pages == d.sources[0].pages
    assert [x.symbol for x in db.list_dossiers(seeded)] == ["PERSISTENT"]
