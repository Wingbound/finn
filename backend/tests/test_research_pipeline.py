import itertools
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from finn import db
from finn.ingest.screener import ScreenerError
from finn.llm.providers import LLMError
from finn.models import IST, Citation, Dossier, Promise, public
from finn.research.docs import DocError
from finn.research.pipeline import build_dossier, is_degraded
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
        if "PROMISES:" in user:
            return {"judgements": []}
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
    assert not is_degraded(d), d.notes
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
    clock = {"t": 0.0}

    def progress(m):
        if m.startswith("Reading Annual Report"):
            clock["t"] = 181.0  # under 60 s of the 240 s budget left once sources are read

    router = FakeRouter(reply)
    d = build_dossier(
        seeded, "PERSISTENT", router, screener_client=FakeScreener(), doc_client=FailingDocs(),
        deadline_s=240, now=lambda: clock["t"], progress=progress,
    )  # fmt: skip
    assert router.calls == []
    assert len(d.sources) == 4
    assert d.trajectory is not None and d.health is not None
    assert d.ledger is None and d.snapshot is None and d.bull == [] and d.bear == []
    assert "Snapshot skipped: build deadline reached" in d.notes
    assert "Ledger skipped: build deadline reached" in d.notes


def test_deadline_margin_skips_sources(seeded):
    clock = itertools.count(0, 10)
    router = FakeRouter(reply)
    d = build_dossier(
        seeded, "PERSISTENT", router, screener_client=FakeScreener(), doc_client=FailingDocs(),
        deadline_s=50, now=lambda: float(next(clock)),
    )  # fmt: skip
    assert d.sources == [] and router.calls == []
    assert "Remaining sources skipped: build deadline reached" in d.notes
    assert is_degraded(d)


def test_deadline_stops_judge_groups(seeded, monkeypatch):
    def one_each(router, src, guard=None, notes=None):
        cit = Citation(source_id=src.id, page=1, quote="x y z a b c d")
        return [Promise(id=f"{src.id}-1", citation=cit, topic="t", kind="qualitative", made_in=src.quarter)]  # fmt: skip

    monkeypatch.setattr("finn.research.pipeline.extract_promises", one_each)
    clock = {"t": 0.0}

    def tick(task, system, user):
        if task == "reason" and "PROMISES:" in user:
            clock["t"] = 181.0  # the first judge call uses up the budget
        return reply(task, system, user)

    router = FakeRouter(tick)
    d = build_dossier(
        seeded, "PERSISTENT", router, screener_client=FakeScreener(), doc_client=FailingDocs(),
        deadline_s=240, now=lambda: clock["t"],
    )  # fmt: skip
    judge_calls = [c for c in router.calls if "PROMISES:" in c[2]]
    assert len(judge_calls) == 1
    assert "Remaining promise checks skipped: build deadline reached" in d.notes
    assert "Snapshot skipped: build deadline reached" in d.notes


def test_stage_failure_becomes_note(seeded, monkeypatch):
    def boom(*a, **k):
        raise ValueError("x")

    monkeypatch.setattr("finn.research.pipeline.snapshot", boom)
    d = build_dossier(
        seeded, "PERSISTENT", FakeRouter(reply), screener_client=FakeScreener(),
        doc_client=FailingDocs(),
    )  # fmt: skip
    assert "Snapshot could not be built (internal error)" in d.notes
    assert not any("ValueError" in n for n in d.notes)
    assert d.ledger is not None
    assert is_degraded(d)


def test_ledger_internal_error_note(seeded, monkeypatch):
    def boom(*a, **k):
        raise KeyError("x")

    monkeypatch.setattr("finn.research.pipeline.build_ledger", boom)
    d = build_dossier(
        seeded, "PERSISTENT", FakeRouter(reply), screener_client=FakeScreener(),
        doc_client=FailingDocs(),
    )  # fmt: skip
    assert "Ledger could not be built (internal error)" in d.notes
    assert not any("KeyError" in n for n in d.notes)


def test_llm_down_everywhere_is_visible(seeded):
    d = build_dossier(
        seeded, "PERSISTENT", FakeRouter(LLMError("503 everywhere")),
        screener_client=FakeScreener(), doc_client=FailingDocs(),
    )  # fmt: skip
    guidance = [n for n in d.notes if n.startswith("Guidance from")]
    assert len(guidance) == 4
    assert all(n.endswith("could not be read (model unavailable)") for n in guidance)
    assert "Snapshot unavailable (model unavailable)" in d.notes
    assert "Bull/bear unavailable (model unavailable)" in d.notes
    assert d.ledger is not None and d.ledger.rows == []
    assert d.ledger.note == "Guidance could not be read from 4 of 4 calls"
    assert is_degraded(d)


def test_guidance_crash_counts_as_unread(seeded, monkeypatch):
    def boom(*a, **k):
        raise ValueError("x")

    monkeypatch.setattr("finn.research.pipeline.extract_promises", boom)
    d = build_dossier(
        seeded, "PERSISTENT", FakeRouter(reply), screener_client=FakeScreener(),
        doc_client=FailingDocs(),
    )  # fmt: skip
    assert "Guidance from Q2 FY27 earnings call (Oct 2026) could not be read (internal error)" in d.notes  # fmt: skip
    assert d.ledger.note == "Guidance could not be read from 4 of 4 calls"


def test_empty_ledger_note_when_calls_have_no_guidance(seeded):
    def none(task, system, user):
        return {"promises": []} if task == "extract_transcript" else reply(task, system, user)

    d = build_dossier(
        seeded, "PERSISTENT", FakeRouter(none), screener_client=FakeScreener(),
        doc_client=FailingDocs(),
    )  # fmt: skip
    assert d.ledger is not None and d.ledger.rows == []
    assert d.ledger.note == "No verifiable forward-looking guidance found in 4 calls"
    assert not is_degraded(d)


def build_stub() -> Dossier:
    return Dossier(
        symbol="X", name=None, basis="consolidated", built_at=datetime.now(IST), sources=[],
        ledger=None, snapshot=None, trajectory=None, health=None, bull=[], bear=[], notes=[],
        cost={}, build_seconds=0.0,
    )  # fmt: skip


def test_is_degraded_markers():
    base = build_stub()
    assert not is_degraded(base)
    for n in (
        "Snapshot unavailable (model unavailable)",
        "Ledger could not be built (internal error)",
        "Guidance from Q2 FY27 call could not be read (internal error)",
        "Remaining sources skipped: build deadline reached",
    ):
        assert is_degraded(base.model_copy(update={"notes": [n]})), n
    ok = base.model_copy(update={"notes": ["Annual report 2026 unavailable: offline"]})
    assert not is_degraded(ok)


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
