from pathlib import Path

from finn.ingest.screener import parse_quarters

FIX = Path(__file__).parent / "fixtures" / "screener"


def _q(name: str) -> dict[str, dict[str, float]]:
    return parse_quarters((FIX / f"{name}_consolidated_quarters.html").read_text())


def test_parse_quarters_tatasteel():
    q = _q("TATASTEEL")
    assert "Dec 2025" in q
    sep = q["Sep 2026"]
    assert sep["Sales"] == 65436.0
    assert sep["Operating Profit"] == 10533.0
    assert sep["Net Profit"] == 3700.0
    assert "Profit before tax" in sep


def test_parse_quarters_skips_percent_and_pdf_rows():
    for name in ("TATASTEEL", "IDFCFIRSTB"):
        for col in _q(name).values():
            assert not any(k.endswith("%") or k == "Raw PDF" for k in col)


def test_parse_quarters_bank_rows():
    assert _q("IDFCFIRSTB")["Sep 2026"]["Revenue"] == 11923.0


def test_parse_quarters_numbers_and_gaps():
    html = (
        "<table><thead><tr><th></th><th>Jun 2026</th><th>Sep 2026</th></tr></thead><tbody>"
        "<tr><td><button>Sales&nbsp;<span>+</span></button></td><td>1,234</td><td></td></tr>"
        "<tr><td>Other Income</td><td>-17</td><td>5</td></tr></tbody></table>"
    )
    assert parse_quarters(html) == {
        "Jun 2026": {"Sales": 1234.0, "Other Income": -17.0},
        "Sep 2026": {"Other Income": 5.0},
    }
