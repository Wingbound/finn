from datetime import datetime

import pytest

from finn import db
from finn.digest import build_digest
from finn.enrich import results
from finn.models import IST, Classification, Filing
from tests.fakes import tatasteel_fake

SUBJECT = (
    "Tata Steel Limited has submitted to the Exchange, the financial results for the "
    "quarter and half year ended September 30, 2026."
)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(results, "_sleep", lambda s: None)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "d.sqlite")
    db.init_db(c)
    results.ingest_financials(c, tatasteel_fake(), ["TATASTEEL"])
    yield c
    c.close()


def _seed(conn, filed_at, category="results", subtype=None, subject=SUBJECT, seq="R1"):
    f = Filing(
        seq_id=seq,
        symbol="TATASTEEL",
        company="Tata Steel Limited",
        nse_desc="Outcome of Board Meeting",
        subject=subject,
        filed_at=filed_at,
    )
    db.upsert_filings(conn, [f])
    db.save_classifications(
        conn,
        {seq: Classification(category=category, subtype=subtype, by="rules", confidence=1.0)},
    )


def _digest(conn, day):
    start = datetime(day.year, day.month, day.day, 0, 0, tzinfo=IST)
    end = datetime(day.year, day.month, day.day, 23, 59, tzinfo=IST)
    return build_digest(
        conn,
        ["TATASTEEL"],
        start,
        end,
        "everything",
        {"results", "press_release"},  # type: ignore[arg-type]
    )


def _stories(d):
    return d["stories"] + [s for v in d["routine"].values() for s in v]


def test_results_story_gets_card(conn):
    _seed(conn, datetime(2026, 11, 7, 13, 6, 33, tzinfo=IST))
    (story,) = _stories(_digest(conn, datetime(2026, 11, 7)))
    assert story.results is not None and story.results.period_label == "Q2 FY27"


def test_card_not_attached_when_dates_far_apart(conn):
    _seed(conn, datetime(2026, 12, 20, 13, 6, 33, tzinfo=IST))
    (story,) = _stories(_digest(conn, datetime(2026, 12, 20)))
    assert story.category == "results" and story.results is None


def test_intimation_story_gets_no_card(conn):
    _seed(conn, datetime(2026, 11, 7, 13, 6, 33, tzinfo=IST), subtype="intimation")
    (story,) = _stories(_digest(conn, datetime(2026, 11, 7)))
    assert story.subtype == "intimation" and story.results is None


def test_non_results_story_untouched(conn):
    _seed(
        conn,
        datetime(2026, 11, 7, 13, 6, 33, tzinfo=IST),
        category="press_release",
        subject="Analyst meet intimation",
    )
    (story,) = _stories(_digest(conn, datetime(2026, 11, 7)))
    assert story.category != "results" and story.results is None
