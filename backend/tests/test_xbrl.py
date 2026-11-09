import json
from datetime import date, datetime
from pathlib import Path

import pytest

from finn.ingest.xbrl import XbrlError, detect_format, parse_filing_list, parse_xbrl
from finn.models import IST

FIX = Path(__file__).parent / "fixtures"


def xml(name: str) -> bytes:
    return (FIX / "xbrl" / name).read_bytes()


def rows() -> list[dict]:
    return json.loads((FIX / "nse" / "integrated_TATASTEEL.json").read_text())["data"]


def sep_cons_row() -> dict:
    return next(
        r for r in rows() if r["qe_Date"] == "30-SEP-2026" and r["consolidated"] == "Consolidated"
    )


def test_parse_tatasteel_q2():
    q = parse_xbrl(xml("TATASTEEL_2026-09-30_cons.xml"), format_hint="indas")
    assert q.symbol == "TATASTEEL"
    assert q.period_start == date(2026, 7, 1)
    assert q.period_end == date(2026, 9, 30)
    assert q.basis == "consolidated"
    assert q.audited is False
    assert q.format == "indas"
    assert q.facts["RevenueFromOperations"] == 654362400000.0
    assert q.facts["ProfitLossForPeriod"] == 36995900000.0


def test_q4_file_picks_the_quarter_not_the_year():
    q = parse_xbrl(xml("TATASTEEL_2026-03-31_cons.xml"))
    assert q.period_start == date(2026, 1, 1)
    assert q.facts["RevenueFromOperations"] == 632701300000.0


def test_q1_file_with_single_context():
    q = parse_xbrl(xml("TATASTEEL_2026-06-30_cons.xml"))
    assert q.period_start == date(2026, 4, 1)
    assert q.facts["RevenueFromOperations"] == 607942900000.0


def test_bank_format_detected_by_elements():
    q = parse_xbrl(xml("IDFCFIRSTB_2026-09-30_sa.xml"))
    assert q.format == "bank"
    assert q.basis == "standalone"
    assert q.facts["InterestEarned"] == 119217500000.0
    assert q.facts["InterestExpended"] == 57373400000.0


def test_nbfc_format_detected_by_elements():
    q = parse_xbrl(xml("BAJFINANCE_2026-09-30_sa.xml"))
    assert q.format == "nbfc"
    assert q.facts["ImpairmentOnFinancialInstruments"] == 21305100000.0


def test_detect_format_from_url():
    base = "https://nsearchives.nseindia.com/corporate/xbrl/"
    assert (
        detect_format(base + "INTEGRATED_FILING_BANKING_1745436_24102026063930_WEB.xml") == "bank"
    )
    assert (
        detect_format(base + "INTEGRATED_FILING_NBFC_INDAS_1742038_19102026075842_WEB.xml")
        == "nbfc"
    )
    assert detect_format(base + "INTEGRATED_FILING_INDAS_1755442_07112026053333_WEB.xml") == "indas"
    assert detect_format("https://x/y.xml") is None


def test_malformed_xml_raises_xbrlerror():
    with pytest.raises(XbrlError):
        parse_xbrl(b"<not xml")


def test_missing_quarter_context_raises():
    raw = xml("TATASTEEL_2026-09-30_cons.xml").decode()
    assert "<xbrli:startDate>2026-07-01</xbrli:startDate>" in raw
    raw = raw.replace(
        "<xbrli:startDate>2026-07-01</xbrli:startDate>",
        "<xbrli:startDate>2026-04-01</xbrli:startDate>",
    )
    with pytest.raises(XbrlError):
        parse_xbrl(raw.encode())


def test_parse_filing_list():
    out = parse_filing_list(rows())
    assert len(out) == 14
    assert out[0].period_end == date(2026, 9, 30)
    f = next(x for x in out if x.period_end == date(2026, 9, 30) and x.basis == "consolidated")
    assert f.filed_at == datetime(2026, 11, 7, 17, 33, 17, tzinfo=IST)
    assert f.format == "indas"
    assert f.audited is False
    assert f.symbol == "TATASTEEL"


def test_parse_filing_list_dedupes_rebroadcasts():
    a = sep_cons_row()
    b = {**a, "broadcast_Date": "07-Nov-2026 18:33:17", "xbrl": a["xbrl"] + "?v=2"}
    out = parse_filing_list([b, a])
    assert len(out) == 1
    # the latest row supplies the document; filed_at stays the first broadcast
    assert out[0].xbrl_url == b["xbrl"]
    assert out[0].filed_at == datetime(2026, 11, 7, 17, 33, 17, tzinfo=IST)
    assert out[0].revised is False


REVISED_URL = (
    "https://nsearchives.nseindia.com/corporate/xbrl/"
    "INTEGRATED_FILING_INDAS_1799999_01122026120000_WEB.xml"
)


def revision_of(row: dict, revised_date: str = "01-DEC-2026 12:00:00", **kw) -> dict:
    """A revised integrated-filing row as NSE lists it: no broadcast, an upper-case month."""
    return {
        **row,
        "broadcast_Date": None,
        "revised_Date": revised_date,
        "revision_Remark": "Revised to correct typographical error",
        "type_Sub": "Revised",
        "xbrl": REVISED_URL,
        **kw,
    }


def test_revision_supersedes_original_but_keeps_its_filed_at():
    orig = sep_cons_row()
    rev = revision_of(orig, audited="Audited")
    out = parse_filing_list([rev, orig])
    assert len(out) == 1
    f = out[0]
    assert f.xbrl_url == REVISED_URL
    assert f.audited is True  # the revision's row supplies url, format and audited
    assert f.format == "indas"
    assert f.revised is True
    assert f.filed_at == datetime(2026, 11, 7, 17, 33, 17, tzinfo=IST)


def test_revision_supersedes_original_in_the_full_list():
    out = parse_filing_list([*rows(), revision_of(sep_cons_row())])
    assert len(out) == 14
    f = next(x for x in out if x.period_end == date(2026, 9, 30) and x.basis == "consolidated")
    assert (f.xbrl_url, f.revised) == (REVISED_URL, True)
    assert f.filed_at == datetime(2026, 11, 7, 17, 33, 17, tzinfo=IST)


def test_revised_only_group_is_kept_with_revision_time():
    out = parse_filing_list([revision_of(sep_cons_row())])
    assert len(out) == 1
    assert out[0].xbrl_url == REVISED_URL
    assert out[0].revised is True
    assert out[0].filed_at == datetime(2026, 12, 1, 12, 0, 0, tzinfo=IST)


def test_upper_case_month_revised_date_parses():
    out = parse_filing_list([revision_of(sep_cons_row(), "31-OCT-2025 23:59:50")])
    assert out[0].filed_at == datetime(2025, 10, 31, 23, 59, 50, tzinfo=IST)


def test_earlier_revision_loses_to_a_later_one():
    orig = sep_cons_row()
    first = revision_of(orig, "20-NOV-2026 10:00:00", xbrl=REVISED_URL + "?first")
    second = revision_of(orig, "01-DEC-2026 12:00:00")
    out = parse_filing_list([second, orig, first])
    assert out[0].xbrl_url == REVISED_URL
    assert out[0].filed_at == datetime(2026, 11, 7, 17, 33, 17, tzinfo=IST)


def test_row_without_any_usable_date_is_dropped():
    orig = sep_cons_row()
    neither = {**orig, "broadcast_Date": None, "revised_Date": None}
    garbled = {**orig, "broadcast_Date": "-", "revised_Date": "soon"}
    assert parse_filing_list([neither, garbled]) == []


def test_unparseable_broadcast_falls_back_to_revised_date():
    row = revision_of(sep_cons_row(), broadcast_Date="not a date")
    out = parse_filing_list([row])
    assert out[0].filed_at == datetime(2026, 12, 1, 12, 0, 0, tzinfo=IST)


def test_parse_filing_list_skips_malformed_rows():
    bad = {**sep_cons_row(), "qe_Date": "-"}
    out = parse_filing_list([bad, *rows()])
    assert len(out) == 14


def test_parse_filing_list_audited_mapping():
    base = sep_cons_row()
    out = parse_filing_list(
        [
            {**base, "audited": "Audited"},
            {**base, "audited": "None", "qe_Date": "30-JUN-2026"},
        ]
    )
    by_end = {f.period_end: f.audited for f in out}
    assert by_end[date(2026, 9, 30)] is True
    assert by_end[date(2026, 6, 30)] is None
