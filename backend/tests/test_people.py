from datetime import datetime

import pytest

from finn import db
from finn.digest import build_digest
from finn.enrich.people import enrich_people, extract_people
from finn.llm.providers import LLMError
from finn.models import IST, Classification, Filing
from tests.fakes import FIXTURES, FakeNSE, FakeRouter

BALAN = (
    "Mr. Jayant Balan is a Mechanical Engineer and PGDM from SP Jain Institute of "
    "Management & Research."
)
URL = "https://nsearchives.nseindia.com/corporate/voltas.pdf"
WHEN = datetime(2026, 11, 5, 10, 0, tzinfo=IST)
SINCE = datetime(2026, 11, 1, tzinfo=IST)


@pytest.fixture(scope="module")
def voltas() -> str:
    return (FIXTURES / "pdf" / "106850979.txt").read_text()


def _filing(seq="V1", pdf_url=URL, summary=None, at=WHEN) -> Filing:
    return Filing(
        seq_id=seq,
        symbol="VOLTAS",
        company="Voltas Limited",
        nse_desc="Change in Directors/ Key Managerial Personnel",
        subject="Appointment and retirement of directors",
        nse_summary=summary,
        pdf_url=pdf_url,
        filed_at=at,
    )


def _seed(conn, f, category="management_change"):
    db.upsert_filings(conn, [f])
    db.save_classifications(
        conn, {f.seq_id: Classification(category=category, by="rules", confidence=1.0)}
    )


def _reply(*people_):
    return {"people": list(people_)}


BALAN_ROW = {
    "name": "Jayant Balan",
    "role": "Managing Director",
    "change": "appointed",
    "effective": "25 May 2027",
    "profile": BALAN,
}
TATA_ROW = {"name": "Noel N. Tata", "role": "Chairman", "change": "retired"}


def test_extract_keeps_grounded_people(voltas):
    router = FakeRouter(
        _reply(
            BALAN_ROW,
            TATA_ROW,
            {"name": "John Doe", "role": "Director", "change": "appointed"},
        )
    )
    out = extract_people(router, _filing(), voltas)
    assert [p.name for p in out] == ["Jayant Balan", "Noel N. Tata"]
    balan, tata = out
    assert balan.incoming and not tata.incoming
    assert balan.profile.startswith("Mr. Jayant Balan is a Mechanical Engineer")
    assert tata.profile is None
    assert balan.source_seq_id == "V1"
    task, _system, user = router.calls[0]
    assert task == "bio"
    assert user.startswith("SUBJECT: Appointment and retirement of directors\n\nFILING TEXT:\n")


def test_fabricated_profile_sentence_dropped(voltas):
    row = {**BALAN_ROW, "profile": BALAN + " He previously ran a unicorn startup in Berlin."}
    out = extract_people(FakeRouter(_reply(row)), _filing(), voltas)
    assert "unicorn" not in out[0].profile
    assert out[0].profile.startswith("Mr. Jayant Balan")


def test_fully_fabricated_profile_becomes_none(voltas):
    row = {**BALAN_ROW, "profile": "A celebrated astronaut."}
    out = extract_people(FakeRouter(_reply(row)), _filing(), voltas)
    assert out[0].profile is None


def test_unknown_change_becomes_other(voltas):
    row = {"name": "Noel N. Tata", "role": "Chairman", "change": "vanished"}
    out = extract_people(FakeRouter(_reply(row)), _filing(), voltas)
    assert out[0].change == "other"
    assert not out[0].incoming


def test_duplicates_by_normalized_name_dropped(voltas):
    rows = [TATA_ROW, {**TATA_ROW, "name": "Mr. Noel N. Tata"}]
    assert len(extract_people(FakeRouter(_reply(*rows)), _filing(), voltas)) == 1


def test_malformed_reply_gives_nothing(voltas):
    assert extract_people(FakeRouter({"people": "nope"}), _filing(), voltas) == []
    assert extract_people(FakeRouter({"people": ["x", {"role": "y"}]}), _filing(), voltas) == []


def test_enrich_saves_and_skips_next_time(conn, voltas):
    _seed(conn, _filing())
    db.save_doc_text(conn, URL, voltas)
    client = FakeNSE({}, {})
    router = FakeRouter(_reply(BALAN_ROW, TATA_ROW))
    res = enrich_people(conn, client, router, SINCE)
    assert (res.done, res.empty, res.failed) == (1, 0, {})
    saved = db.get_enrichments(conn, ["V1"], "people")["V1"]
    assert [p["name"] for p in saved["people"]] == ["Jayant Balan", "Noel N. Tata"]
    model = conn.execute("SELECT model FROM enrichments").fetchone()["model"]
    assert model == "groq/openai/gpt-oss-120b"
    assert client.byte_calls == []
    res2 = enrich_people(conn, client, router, SINCE)
    assert (res2.done, res2.empty) == (0, 0)
    assert len(router.calls) == 1


def test_enrich_ignores_other_categories_and_old_filings(conn, voltas):
    _seed(conn, _filing("V1"), category="results")
    _seed(conn, _filing("V2", at=datetime(2026, 10, 1, tzinfo=IST)))
    router = FakeRouter(_reply())
    enrich_people(conn, FakeNSE({}, {}), router, SINCE)
    assert router.calls == []


def test_no_text_saved_as_empty(conn):
    _seed(conn, _filing(pdf_url=None, summary=None))
    router = FakeRouter(_reply(BALAN_ROW))
    res = enrich_people(conn, FakeNSE({}, {}), router, SINCE)
    assert (res.done, res.empty) == (0, 1)
    assert db.get_enrichments(conn, ["V1"], "people")["V1"] == {"people": [], "reason": "no text"}
    assert router.calls == []


def test_summary_used_when_no_pdf(conn):
    _seed(conn, _filing(pdf_url=None, summary="Noel N. Tata retires as Chairman."))
    router = FakeRouter(_reply(TATA_ROW))
    res = enrich_people(conn, FakeNSE({}, {}), router, SINCE)
    assert res.done == 1
    assert db.get_enrichments(conn, ["V1"], "people")["V1"]["people"][0]["name"] == "Noel N. Tata"


def test_llm_error_not_saved_then_retried(conn, voltas):
    _seed(conn, _filing())
    db.save_doc_text(conn, URL, voltas)
    res = enrich_people(conn, FakeNSE({}, {}), FakeRouter(LLMError("all providers down")), SINCE)
    assert res.done == 0 and "V1" in res.failed
    assert db.get_enrichments(conn, ["V1"], "people") == {}
    ok = FakeRouter(_reply(TATA_ROW))
    assert enrich_people(conn, FakeNSE({}, {}), ok, SINCE).done == 1


def test_nse_error_not_saved(conn):
    _seed(conn, _filing())
    res = enrich_people(conn, FakeNSE({}, {}), FakeRouter(_reply()), SINCE)
    assert "V1" in res.failed
    assert db.get_enrichments(conn, ["V1"], "people") == {}


def test_digest_attaches_people_incoming_first(conn):
    _seed(conn, _filing("V1"))
    _seed(conn, _filing("V2", at=datetime(2026, 11, 5, 11, 0, tzinfo=IST)))
    row = lambda name, change, seq: {
        "name": name,
        "role": None,
        "change": change,
        "effective": None,
        "profile": None,
        "incoming": change in {"appointed", "redesignated"},
        "source_seq_id": seq,
    }
    db.save_enrichment(
        conn, "V1", "people", {"people": [row("Noel N. Tata", "retired", "V1")]}, "m"
    )
    db.save_enrichment(
        conn,
        "V2",
        "people",
        {
            "people": [
                row("Mr. Noel N. Tata", "retired", "V2"),
                row("Jayant Balan", "appointed", "V2"),
            ]
        },
        "m",
    )
    d = build_digest(
        conn,
        ["VOLTAS"],
        datetime(2026, 11, 5, 0, 0, tzinfo=IST),
        datetime(2026, 11, 5, 23, 59, tzinfo=IST),
        "everything",
        {"management_change"},
    )
    stories = [s for s in d["stories"] if s.category == "management_change"]
    assert len(stories) == 1
    assert [p.name for p in stories[0].people] == ["Jayant Balan", "Noel N. Tata"]
    assert stories[0].people[0].incoming
