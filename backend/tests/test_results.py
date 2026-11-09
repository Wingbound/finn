from datetime import date
from pathlib import Path

import pytest

from finn.enrich.results import (
    build_card,
    pct_change,
    quarter_end_shift,
    quarter_label,
)
from finn.ingest.xbrl import QuarterFinancials, parse_xbrl

FX = Path(__file__).parent / "fixtures" / "xbrl"


def load(name: str, hint=None) -> QuarterFinancials:
    return parse_xbrl((FX / name).read_bytes(), format_hint=hint)


def tata(period: str) -> QuarterFinancials:
    return load(f"TATASTEEL_{period}_cons.xml", "indas")


def by_key(rows):
    return {r.key: r for r in rows}


def test_quarter_label():
    assert quarter_label(date(2026, 9, 30)) == "Q2 FY27"
    assert quarter_label(date(2026, 3, 31)) == "Q4 FY26"
    assert quarter_label(date(2026, 6, 30)) == "Q1 FY27"
    assert quarter_label(date(2025, 12, 31)) == "Q3 FY26"


def test_quarter_end_shift():
    assert quarter_end_shift(date(2026, 9, 30), -1) == date(2026, 6, 30)
    assert quarter_end_shift(date(2026, 9, 30), -4) == date(2025, 9, 30)
    assert quarter_end_shift(date(2026, 3, 31), -1) == date(2025, 12, 31)


def test_pct_change_rules():
    assert pct_change(110, 100) == 10.0
    assert pct_change(5, -3) is None
    assert pct_change(5, 0) is None
    assert pct_change(None, 3) is None
    assert pct_change(float("nan"), 3) is None


def test_tatasteel_q2_card():
    card = build_card(tata("2026-09-30"), tata("2026-06-30"), tata("2025-09-30"), ["u1", "u2"])
    assert card.period_label == "Q2 FY27"
    assert card.basis == "consolidated"
    assert card.compared_qoq == date(2026, 6, 30)
    assert card.compared_yoy == date(2025, 9, 30)
    assert card.sources == ["u1", "u2"]
    m = by_key(card.metrics)
    exp = {
        "revenue": (65436.24, 7.6, 11.5),
        "ebitda": (10533.07, 13.7, 18.4),
        "pbt": (5342.88, 42.8, 28.1),
        "pat": (3699.59, 55.1, 16.2),
    }
    assert [r.key for r in card.metrics] == list(exp)
    for k, (v, q, y) in exp.items():
        assert m[k].value == pytest.approx(v, abs=0.01)
        assert m[k].qoq_pct == pytest.approx(q, abs=0.06)
        assert m[k].yoy_pct == pytest.approx(y, abs=0.06)
    assert m["ebitda"].computed is True
    assert m["revenue"].computed is False
    g = by_key(card.margins)
    assert g["ebitda_margin"].value_pct == pytest.approx(16.1, abs=0.06)
    assert g["ebitda_margin"].qoq_bps == pytest.approx(86, abs=1)
    assert g["ebitda_margin"].yoy_bps == pytest.approx(94, abs=1)
    assert g["pat_margin"].qoq_bps == pytest.approx(173, abs=1)
    assert g["pat_margin"].yoy_bps == pytest.approx(23, abs=1)
    # XBRL sign convention: PBT = profit before exceptional items + ExceptionalItemsBeforeTax
    assert "PBT includes an exceptional gain of ₹348.68 cr." in card.notes
    assert "PAT includes ₹112.27 cr share of profit of associates and joint ventures." in card.notes
    assert not any("No QoQ" in n or "No YoY" in n for n in card.notes)


def test_bank_card_idfc():
    card = build_card(
        load("IDFCFIRSTB_2026-09-30_sa.xml"),
        load("IDFCFIRSTB_2026-06-30_sa.xml"),
        None,
        [],
    )
    assert card.format == "bank"
    assert [r.key for r in card.metrics] == [
        "interest_earned", "nii", "ppop", "provisions",
        "pbt", "pat", "gnpa", "nnpa",
    ]  # fmt: skip
    m = by_key(card.metrics)
    assert m["nii"].value == pytest.approx(6184.41, abs=0.01)
    assert m["nii"].qoq_pct == pytest.approx(3.5, abs=0.06)
    assert m["pat"].value == pytest.approx(1044.60, abs=0.01)
    assert m["pat"].qoq_pct == pytest.approx(-2.8, abs=0.06)
    assert all(r.yoy_pct is None for r in card.metrics)
    assert card.compared_yoy is None
    assert any("No YoY comparison" in n for n in card.notes)
    assert (
        "Banks are shown on net interest income and pre-provision profit; EBITDA does not apply."
        in card.notes
    )
    assert not any("exceptional" in n for n in card.notes)  # the fixture's item is 0
    assert card.margins == []


def test_nbfc_card_bajaj():
    card = build_card(load("BAJFINANCE_2026-09-30_sa.xml"), None, None, [])
    assert card.format == "nbfc"
    m = by_key(card.metrics)
    assert m["nii"].value == pytest.approx(12150.30, abs=0.01)
    assert m["impairment"].value == pytest.approx(2130.51, abs=0.01)
    assert m["pat"].value == pytest.approx(5536.10, abs=0.01)
    assert all(r.qoq_pct is None and r.yoy_pct is None for r in card.metrics)
    assert card.compared_qoq is None
    assert any("No QoQ comparison" in n for n in card.notes)
    assert (
        "NBFCs are shown on net interest income and credit cost; EBITDA does not apply."
        in card.notes
    )


def test_negative_exceptional_is_a_loss():
    q = tata("2026-06-30")
    assert q.facts["ExceptionalItemsBeforeTax"] == -3454800000.0
    card = build_card(q, None, None, [])
    assert "PBT includes an exceptional loss of ₹345.48 cr." in card.notes
    assert not any("exceptional gain" in n for n in card.notes)


def test_nbfc_exceptional_uses_gain_or_loss():
    q = load("BAJFINANCE_2026-09-30_sa.xml").model_copy(deep=True)
    q.facts["ExceptionalItemsBeforeTax"] = -1.5e9
    card = build_card(q, None, None, [])
    assert "PBT includes an exceptional loss of ₹150.00 cr." in card.notes


@pytest.mark.parametrize(
    ("value", "note"),
    [
        (-1.5e9, "PBT includes exceptional items of −₹150.00 cr."),
        (2.5e9, "PBT includes exceptional items of ₹250.00 cr."),
    ],
)
def test_bank_exceptional_note_is_neutral_and_signed(value, note):
    q = load("IDFCFIRSTB_2026-09-30_sa.xml").model_copy(deep=True)
    q.facts["ExceptionalItems"] = value
    card = build_card(q, None, None, [])
    assert note in card.notes
    assert not any("gain" in n or "loss of" in n for n in card.notes)


def test_negative_associates_share_is_a_loss():
    q = tata("2026-09-30").model_copy(deep=True)
    q.facts["ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod"] = -5e8
    card = build_card(q, None, None, [])
    assert "PAT includes a ₹50.00 cr share of loss of associates and joint ventures." in card.notes


def test_format_mismatch_is_ignored():
    cur = tata("2026-09-30")
    prev = tata("2026-06-30").model_copy(update={"format": "nbfc"})
    year_ago = tata("2025-09-30").model_copy(update={"format": "bank"})
    card = build_card(cur, prev, year_ago, [])
    assert card.compared_qoq is None and card.compared_yoy is None
    assert all(r.qoq_pct is None and r.yoy_pct is None for r in card.metrics)
    assert any("No QoQ comparison" in n for n in card.notes)
    assert any("No YoY comparison" in n for n in card.notes)


def test_missing_element_gives_none_row():
    q = tata("2026-09-30")
    q.facts.pop("DepreciationDepletionAndAmortisationExpense")
    card = build_card(q, None, None, [])
    m = by_key(card.metrics)
    assert m["ebitda"].value is None
    assert by_key(card.margins)["ebitda_margin"].value_pct is None
    assert m["revenue"].value == pytest.approx(65436.24, abs=0.01)


def test_nonfinite_fact_is_missing():
    q = tata("2026-09-30")
    q.facts["ProfitBeforeTax"] = float("nan")
    card = build_card(q, tata("2026-06-30"), None, [])
    assert by_key(card.metrics)["pbt"].value is None
    assert by_key(card.metrics)["pbt"].qoq_pct is None


def test_sign_change_has_note_not_pct():
    cur = tata("2026-09-30")
    prev = tata("2026-06-30").model_copy(deep=True)
    prev.facts["ProfitLossForPeriod"] = -5e9
    card = build_card(cur, prev, None, [])
    assert by_key(card.metrics)["pat"].qoq_pct is None
    assert any("PAT turned positive vs Q1 FY27" in n for n in card.notes)


def test_swing_to_loss_note():
    cur = tata("2026-09-30").model_copy(deep=True)
    cur.facts["ProfitLossForPeriod"] = -5e9
    card = build_card(cur, tata("2026-06-30"), None, [])
    assert any("PAT swung to a loss vs Q1 FY27" in n for n in card.notes)


def test_basis_mismatch_is_ignored():
    cur = tata("2026-09-30")
    prev = tata("2026-06-30").model_copy(update={"basis": "standalone"})
    card = build_card(cur, prev, None, [])
    assert card.compared_qoq is None
    assert any("No QoQ comparison" in n for n in card.notes)
