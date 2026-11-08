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


def test_parse_filing_list_dedupes_revisions():
    a = sep_cons_row()
    b = {**a, "broadcast_Date": "07-Nov-2026 18:33:17"}
    out = parse_filing_list([a, b])
    assert len(out) == 1
    assert out[0].filed_at == datetime(2026, 11, 7, 18, 33, 17, tzinfo=IST)


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
