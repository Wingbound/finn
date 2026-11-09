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


def test_parse_quarters_ignores_other_sections_of_a_full_page():
    quarters = (FIX / "TATASTEEL_consolidated_quarters.html").read_text()
    page = (
        '<html><body><section id="top"><table><thead><tr><th></th><th>Mar 2019</th></tr>'
        "</thead><tbody><tr><td>Sales</td><td>1</td></tr></tbody></table></section>"
        + quarters
        + '<section id="profit-loss"><table><thead><tr><th></th><th>Mar 2020</th>'
        "<th>Mar 2021</th></tr></thead><tbody><tr><td>Sales</td><td>999</td><td>888</td></tr>"
        "<tr><td>Net Profit</td><td>7</td><td>8</td></tr></tbody></table></section></body></html>"
    )
    q = parse_quarters(page)
    assert q["Sep 2026"]["Sales"] == 65436.0
    # (the real quarters table already has Mar 2025/Mar 2026 columns, so the decoys use older years)
    assert not {"Mar 2019", "Mar 2020", "Mar 2021"} & set(q)
    assert q["Mar 2025"]["Sales"] != 999.0 and 999.0 not in q["Sep 2026"].values()


# --- company tables, documents, search (Plan 3) ---

import httpx
import pytest
import respx

from finn.ingest.screener import (
    ScreenerError,
    fetch_company,
    parse_documents,
    parse_name,
    parse_table,
    search,
)

SALES_MAR26 = 14748.0
OPM_MAR26 = 19.0
PAGE = (Path(__file__).parent / "fixtures" / "research" / "PERSISTENT_screener.html").read_text()


def test_parse_quarters_is_parse_table():
    html = (FIX / "TATASTEEL_consolidated_quarters.html").read_text()
    assert parse_quarters(html) == parse_table(html, "quarters", keep_pct=False)


def test_parse_profit_loss():
    pl = parse_table(PAGE, "profit-loss")
    assert "Mar 2026" in pl and "TTM" in pl
    for row in ("Sales", "Operating Profit", "OPM %", "Net Profit"):
        assert row in pl["Mar 2026"]
    assert pl["Mar 2026"]["Sales"] == SALES_MAR26
    assert pl["Mar 2026"]["OPM %"] == OPM_MAR26


def test_parse_balance_sheet_and_cash_flow_and_ratios():
    assert {"Borrowings", "Reserves"} <= set(parse_table(PAGE, "balance-sheet")["Mar 2026"])
    cf = parse_table(PAGE, "cash-flow")["Mar 2026"]
    assert "Free Cash Flow" in cf and "CFO/EBITDA" in cf
    assert "Working Capital Days" in parse_table(PAGE, "ratios")["Mar 2026"]


def test_parse_table_missing_section_in_full_page_is_empty():
    assert parse_table(PAGE.replace('id="profit-loss"', 'id="x"'), "profit-loss") == {}


def test_parse_documents():
    d = parse_documents(PAGE)
    assert len(d["concalls"]) >= 4
    assert d["concalls"][0]["date"] == "Oct 2026"
    assert d["concalls"][0]["transcript_url"].startswith("https://")
    assert d["concalls"][0]["ppt_url"]
    assert any(c["transcript_url"] is None for c in d["concalls"])  # unposted ones
    assert d["annual_reports"][0]["year"] == 2026
    assert all(isinstance(a["year"], int) for a in d["annual_reports"])
    urls = [c["transcript_url"] for c in d["concalls"]] + [a["url"] for a in d["annual_reports"]]
    assert not any(u and "&amp;" in u for u in urls)


def test_parse_name():
    assert "Persistent" in parse_name(PAGE)
    assert parse_name("<html></html>") is None


@respx.mock
def test_search_parses_symbol():
    route = respx.get("https://www.screener.in/api/company/search/")
    route.respond(
        json=[
            {
                "id": 2458,
                "name": "Persistent Systems Ltd",
                "url": "/company/PERSISTENT/consolidated/",
            }
        ]
    )
    assert search("persistent") == [
        {
            "name": "Persistent Systems Ltd",
            "symbol": "PERSISTENT",
            "url": "/company/PERSISTENT/consolidated/",
        }
    ]
    route.respond(json=[])
    assert search("zzzz") == []
    route.respond(500)
    with pytest.raises(ScreenerError):
        search("x", client=httpx.Client())


@respx.mock
def test_fetch_company_falls_back_to_standalone():
    respx.get("https://www.screener.in/company/ABC/consolidated/").respond(
        text='<section id="profit-loss"><table><thead><tr><th></th></tr></thead></table></section>'
    )
    respx.get("https://www.screener.in/company/ABC/").respond(text=PAGE)
    html, basis = fetch_company("ABC")
    assert basis == "standalone" and html == PAGE


@respx.mock
def test_fetch_company_consolidated_and_errors():
    respx.get("https://www.screener.in/company/P/consolidated/").respond(text=PAGE)
    assert fetch_company("P")[1] == "consolidated"
    respx.get("https://www.screener.in/company/N/consolidated/").respond(404)
    respx.get("https://www.screener.in/company/N/").respond(404)
    with pytest.raises(ScreenerError):
        fetch_company("N")
