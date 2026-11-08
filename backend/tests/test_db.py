from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from finn import db
from finn.models import Classification, Filing, PriceBar

IST = timezone(timedelta(hours=5, minutes=30))


def make_filing(seq: str, symbol: str = "TRENT", filed_at: datetime | None = None) -> Filing:
    return Filing(
        seq_id=seq,
        symbol=symbol,
        company=f"{symbol} Ltd",
        nse_desc="Outcome of Board Meeting",
        subject="Board meeting outcome",
        nse_summary=None,
        pdf_url=None,
        filed_at=filed_at or datetime(2026, 11, 3, 10, 0, tzinfo=IST),
        has_xbrl=False,
    )


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "sub" / "finn.sqlite")
    db.init_db(c)
    yield c
    c.close()


def test_upsert_is_idempotent(conn):
    filings = [make_filing(str(i)) for i in range(3)]
    assert db.upsert_filings(conn, filings) == 3
    assert db.upsert_filings(conn, filings) == 0


def test_classification_survives_reupsert(conn):
    f = make_filing("1")
    db.upsert_filings(conn, [f])
    assert [x.seq_id for x in db.unclassified_filings(conn)] == ["1"]
    cls = Classification(category="results", subtype="q2", noise=False, by="rules", confidence=0.9)
    db.save_classifications(conn, {"1": cls})
    assert db.upsert_filings(conn, [f]) == 0
    assert db.unclassified_filings(conn) == []
    rows = db.filings_in_window(conn, ["TRENT"], f.filed_at - timedelta(days=1), f.filed_at)
    assert rows == [(f, cls)]


def test_window_filters_symbol_and_time(conn):
    inside = make_filing("a", filed_at=datetime(2026, 11, 3, 23, 59, tzinfo=IST))
    outside = make_filing("b", filed_at=datetime(2026, 11, 4, 0, 0, tzinfo=IST))
    other = make_filing("c", symbol="TECHM", filed_at=datetime(2026, 11, 3, 12, 0, tzinfo=IST))
    early = make_filing("d", filed_at=datetime(2026, 11, 2, 23, 59, tzinfo=IST))
    utc = make_filing("e", filed_at=datetime(2026, 11, 3, 3, 0, tzinfo=UTC))  # 08:30 IST
    db.upsert_filings(conn, [inside, outside, other, early, utc])
    start = datetime(2026, 11, 3, 0, 0, tzinfo=IST)
    end = datetime(2026, 11, 3, 23, 59, 59, tzinfo=IST)
    rows = db.filings_in_window(conn, ["TRENT"], start, end)
    assert [f.seq_id for f, _ in rows] == ["a", "e"]
    assert all(c is None for _, c in rows)
    assert rows[1][0].filed_at.utcoffset() == timedelta(hours=5, minutes=30)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        make_filing("x", filed_at=datetime(2026, 11, 3, 10, 0))


def test_price_history_ascending_and_limited(conn):
    bars = [PriceBar(symbol="TRENT", date=date(2026, 11, d), open=1, high=2, low=1, close=1.5, volume=100 + d)
            for d in range(1, 8)]
    assert db.upsert_prices(conn, bars) == 7
    assert db.upsert_prices(conn, bars) == 0
    hist = db.price_history(conn, "TRENT", limit=3)
    assert [b.date.day for b in hist] == [5, 6, 7]


def test_meta_roundtrip(conn):
    assert db.get_meta(conn, "k") is None
    db.set_meta(conn, "k", "v1")
    db.set_meta(conn, "k", "v2")
    assert db.get_meta(conn, "k") == "v2"


def test_llm_tables_exist(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"filings", "prices", "meta", "llm_cache", "llm_calls"} <= names


def test_get_filing(conn):
    f = Filing(seq_id="g1", symbol="TCS", company="TCS", nse_desc="d", subject="s",
               filed_at=datetime(2026, 11, 1, 10, 0, tzinfo=IST))
    db.upsert_filings(conn, [f])
    got, cls = db.get_filing(conn, "g1")
    assert got == f and cls is None
    assert db.get_filing(conn, "missing") is None
