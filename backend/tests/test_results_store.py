from datetime import date, datetime

import pytest

from finn import db
from finn.enrich import results
from finn.models import IST
from tests.fakes import FakeNSE, tatasteel_fake


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(results, "_sleep", lambda s: None)


def _periods(conn):
    return [
        (r["period_end"], r["basis"])
        for r in conn.execute("SELECT * FROM financials ORDER BY period_end DESC")
    ]


def test_ingest_stores_current_prev_and_year_ago(conn):
    res = results.ingest_financials(conn, tatasteel_fake(), ["TATASTEEL"])
    assert res.fetched == 3 and res.skipped == 0 and res.failed == {}
    assert _periods(conn) == [
        ("2026-09-30", "consolidated"),
        ("2026-06-30", "consolidated"),
        ("2025-09-30", "consolidated"),
    ]


def test_second_ingest_skips_stored_urls(conn):
    fake = tatasteel_fake()
    results.ingest_financials(conn, fake, ["TATASTEEL"])
    fake.byte_calls.clear()
    res = results.ingest_financials(conn, fake, ["TATASTEEL"])
    assert (res.fetched, res.skipped) == (0, 3)
    assert fake.byte_calls == []


def test_failing_symbol_does_not_stop_others(conn):
    fake = tatasteel_fake()
    res = results.ingest_financials(conn, fake, ["BROKEN", "TATASTEEL"])
    assert "BROKEN" in res.failed and "NSEUnavailable" in res.failed["BROKEN"]
    assert db.latest_financials(conn, "TATASTEEL") is not None


def test_empty_list_is_failure(conn):
    fake = FakeNSE({"X": []}, {})
    res = results.ingest_financials(conn, fake, ["X"])
    assert res.failed == {"X": "no financials filings"}


def test_bad_target_fails_only_that_target(conn):
    fake = tatasteel_fake()
    prev_url = next(
        r["xbrl"]
        for r in fake.rows["TATASTEEL"]
        if r["qe_Date"].upper() == "30-JUN-2026" and r["consolidated"] == "Consolidated"
    )
    fake.files[prev_url] = b"<not xml"
    res = results.ingest_financials(conn, fake, ["TATASTEEL"])
    assert res.fetched == 2 and "TATASTEEL" in res.failed
    assert "XbrlError" in res.failed["TATASTEEL"]
    assert len(_periods(conn)) == 2


def test_card_for_builds_from_store(conn):
    results.ingest_financials(conn, tatasteel_fake(), ["TATASTEEL"])
    out = results.card_for(conn, "TATASTEEL")
    assert out is not None
    card, filed_at = out
    assert card.period_label == "Q2 FY27"
    rev = next(m for m in card.metrics if m.key == "revenue")
    assert rev.qoq_pct == pytest.approx(7.6, abs=0.05)
    assert filed_at == datetime(2026, 11, 7, 17, 33, 17, tzinfo=IST)
    assert len(card.sources) == 3
    assert card.compared_qoq == date(2026, 6, 30)
    assert card.compared_yoy == date(2025, 9, 30)


def test_card_for_unknown_symbol_is_none(conn):
    assert results.card_for(conn, "NOPE") is None


def _as_standalone(xml: bytes) -> bytes:
    old = b">Consolidated</in-capmkt:NatureOfReportStandaloneConsolidated>"
    assert old in xml
    return xml.replace(old, old.replace(b"Consolidated", b"Standalone", 1))


def _standalone_fake(rows_only_standalone=True):
    fake = tatasteel_fake()
    rows, files = [], {}
    for r in fake.rows["TATASTEEL"]:
        if r["xbrl"] in fake.files:
            r = dict(r, consolidated="Standalone")
            rows.append(r)
            files[r["xbrl"]] = _as_standalone(fake.files[r["xbrl"]])
    return FakeNSE({"TATASTEEL": rows}, files)


def test_ingest_falls_back_to_standalone(conn):
    res = results.ingest_financials(conn, _standalone_fake(), ["TATASTEEL"])
    assert res.failed == {} and res.fetched == 3
    for pe in (date(2026, 9, 30), date(2026, 6, 30), date(2025, 9, 30)):
        got = db.get_financials(conn, "TATASTEEL", pe, "standalone")
        assert got is not None and got[0].basis == "standalone"
    card, _ = results.card_for(conn, "TATASTEEL")
    assert card.basis == "standalone"


def test_standalone_basis_stored(conn):
    results.ingest_financials(conn, _standalone_fake(), ["TATASTEEL"])
    assert {b for _, b in _periods(conn)} == {"standalone"}
    assert db.latest_financials(conn, "TATASTEEL")[1] == "standalone"


def test_basis_mismatch_target_is_skipped_and_recorded(conn):
    fake = _standalone_fake()
    cons = tatasteel_fake()
    url = next(iter(fake.files))
    fake.files[url] = cons.files[url]  # consolidated doc behind a Standalone row
    res = results.ingest_financials(conn, fake, ["TATASTEEL"])
    assert "basis mismatch" in res.failed["TATASTEEL"]
    assert res.fetched == 2 and len(_periods(conn)) == 2


def test_rows_stored_under_requested_symbol(conn):
    fake = tatasteel_fake()
    for url, xml in fake.files.items():
        fake.files[url] = xml.replace(
            b'contextRef="OneD">TATASTEEL<', b'contextRef="OneD">tatasteel<'
        )
    results.ingest_financials(conn, fake, ["TATASTEEL"])
    assert results.card_for(conn, "TATASTEEL") is not None
    assert len(_periods(conn)) == 3
