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


REVISED_URL = (
    "https://nsearchives.nseindia.com/corporate/xbrl/"
    "INTEGRATED_FILING_INDAS_1799999_01122026120000_WEB.xml"
)
_SEP_REVENUE = b'unitRef="INR">654362400000<'


def _sep_cons(fake: FakeNSE) -> dict:
    return next(
        r
        for r in fake.rows["TATASTEEL"]
        if r["qe_Date"].upper() == "30-SEP-2026" and r["consolidated"] == "Consolidated"
    )


def _add_revision(fake: FakeNSE, *, drop_original: bool = False) -> bytes:
    """List a revised Sep-2026 consolidated row (broadcast null) whose revenue is restated."""
    orig = _sep_cons(fake)
    xml = fake.files[orig["xbrl"]]
    assert _SEP_REVENUE in xml
    revised_xml = xml.replace(_SEP_REVENUE, b'unitRef="INR">654000000000<')
    rev = {
        **orig,
        "broadcast_Date": None,
        "revised_Date": "01-DEC-2026 12:00:00",
        "revision_Remark": "Revised to correct typographical error",
        "type_Sub": "Revised",
        "xbrl": REVISED_URL,
    }
    rows = [r for r in fake.rows["TATASTEEL"] if not (drop_original and r is orig)]
    fake.rows["TATASTEEL"] = [*rows, rev]
    fake.files[REVISED_URL] = revised_xml
    return revised_xml


def test_revision_replaces_stored_original_on_next_ingest(conn):
    fake = tatasteel_fake()
    results.ingest_financials(conn, fake, ["TATASTEEL"])
    orig_url = _sep_cons(fake)["xbrl"]
    assert db.get_financials(conn, "TATASTEEL", date(2026, 9, 30), "consolidated")[2] == orig_url

    _add_revision(fake)
    fake.byte_calls.clear()
    res = results.ingest_financials(conn, fake, ["TATASTEEL"])
    assert (res.fetched, res.skipped, res.failed) == (1, 2, {})
    assert fake.byte_calls == [REVISED_URL]
    q, filed_at, url = db.get_financials(conn, "TATASTEEL", date(2026, 9, 30), "consolidated")
    assert url == REVISED_URL
    assert q.facts["RevenueFromOperations"] == 654000000000.0
    # the card keeps the first broadcast's time, so it still attaches to the results story
    assert filed_at == datetime(2026, 11, 7, 17, 33, 17, tzinfo=IST)
    assert len(_periods(conn)) == 3


def test_revised_only_newest_period_keeps_consolidated(conn):
    fake = tatasteel_fake()
    _add_revision(fake, drop_original=True)
    res = results.ingest_financials(conn, fake, ["TATASTEEL"])
    assert res.failed == {} and res.fetched == 3
    assert _periods(conn)[0] == ("2026-09-30", "consolidated")
    _, filed_at, url = db.get_financials(conn, "TATASTEEL", date(2026, 9, 30), "consolidated")
    assert url == REVISED_URL
    assert filed_at == datetime(2026, 12, 1, 12, 0, 0, tzinfo=IST)


def test_period_mismatch_target_is_skipped_and_recorded(conn):
    fake = tatasteel_fake()
    sep_url = _sep_cons(fake)["xbrl"]
    jun_url = next(
        r["xbrl"]
        for r in fake.rows["TATASTEEL"]
        if r["qe_Date"].upper() == "30-JUN-2026" and r["consolidated"] == "Consolidated"
    )
    fake.files[sep_url] = fake.files[jun_url]  # a Jun-2026 document behind the Sep-2026 row
    res = results.ingest_financials(conn, fake, ["TATASTEEL"])
    assert res.failed["TATASTEEL"] == (
        "2026-09-30 period mismatch: list 2026-09-30, document 2026-06-30"
    )
    assert res.fetched == 2
    assert db.get_financials(conn, "TATASTEEL", date(2026, 9, 30), "consolidated") is None


def test_missing_target_is_recorded_not_on_file(conn):
    fake = tatasteel_fake()
    fake.rows["TATASTEEL"] = [
        r
        for r in fake.rows["TATASTEEL"]
        if not (r["qe_Date"].upper() == "30-SEP-2025" and r["consolidated"] == "Consolidated")
    ]
    res = results.ingest_financials(conn, fake, ["TATASTEEL"])
    assert res.failed == {"TATASTEEL": "2025-09-30 not on file"}
    assert res.fetched == 2
