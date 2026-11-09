import json

from finn.llm.providers import LLMError
from finn.models import BalanceSheetHealth, Flag, Ledger, Source, Trajectory
from finn.research.synthesis import bull_bear, facts_block, snapshot
from tests.fakes import FIXTURES, FakeRouter

REAL_A = "Q2 FY27 revenue stood at USD 487.6 million, registering a year-on-year growth of 20%."
REAL_B = (
    "In terms of financing, we intend replacing the Euro 1.4 billion 18-month bridge loan "
    "with longer tenure, capital and favorable terms."
)


def sources() -> list[Source]:
    data = json.loads((FIXTURES / "research" / "PERSISTENT_transcripts.json").read_text())
    return [
        Source(
            id="PERSISTENT-T1",
            kind="transcript",
            title="Q2 FY27 call",
            quarter="Q2 FY27",
            url=data[0]["url"],
            pages=data[0]["pages"],
        )
    ]


def item(text, quote, page=8, sid="PERSISTENT-T1"):
    return {"text": text, "quote": quote, "source_id": sid, "page": page}


def analytics():
    traj = Trajectory(
        years=["Mar 2022", "Mar 2026"], revenue=[1.0, 2.0], operating_profit=[1.0, 1.0],
        margin_pct=[1.0, 1.0], pat=[1.0, 1.0], revenue_cagr_pct=18.2, pat_cagr_pct=None,
        margin_change_bps=120, read="growing", lender=False,
    )  # fmt: skip
    health = BalanceSheetHealth(
        as_of="Mar 2026", debt_to_equity=0.06, cfo_to_pat_3y=0.97, fcf_3y_cr=3483.0,
        working_capital_days=None, wc_days_change_3y=None, roce_pct=None,
        flags=[Flag(level="good", text="Net cash balance sheet")],
    )  # fmt: skip
    ledger = Ledger(
        rows=[], counts={"kept": 3, "partly": 1, "missed": 2, "pending": 4, "dropped": 0},
        credibility_pct=62.5,
    )  # fmt: skip
    return ledger, traj, health


def test_facts_block_lines_and_skips_none():
    ledger, traj, health = analytics()
    f = facts_block(traj, health, ledger)
    assert "Revenue CAGR (Mar 2022–Mar 2026): 18.2%" in f
    assert "Operating margin change: +120 bps" in f
    assert "Debt to equity: 0.06" in f
    assert "Free cash flow (3y): ₹3,483 cr" in f
    assert (
        "Promise ledger: 3 kept, 1 partly, 2 missed, 4 pending, 0 dropped (credibility 62.5%)" in f
    )
    assert "Net cash balance sheet" in f
    assert "ROCE" not in f and "Working capital" not in f


def test_snapshot_keeps_real_quote_drops_invented():
    r = FakeRouter(
        {
            "summary": [
                item("Revenue grew twenty percent year on year.", REAL_A),
                item("The firm sells rocket engines to Mars colonies.", "We sell rocket engines to Mars colonies daily."),
            ]
        }
    )  # fmt: skip
    guard: dict = {}
    s = snapshot(r, sources(), guard=guard)
    assert s is not None and len(s.summary) == 1
    assert s.summary[0].citation.page == 8
    assert guard == {"points_proposed": 2, "points_kept": 1}
    assert r.calls[0][0] == "reason"


def test_snapshot_none_when_nothing_survives_or_llm_error():
    assert (
        snapshot(
            FakeRouter(
                {"summary": [item("Bad one here.", "nonsense words not in any source ever")]}
            ),
            sources(),
        )
        is None
    )
    assert snapshot(FakeRouter(LLMError("x")), sources()) is None  # fmt: skip


def test_bull_point_number_from_facts_kept_invented_dropped():
    ledger, traj, health = analytics()
    r = FakeRouter(
        {
            "bull": [
                item("Revenue compounding at 18.2% with growth continuing.", REAL_A),
                item("Revenue compounding at 99.9% with growth continuing.", REAL_A),
            ],
            "bear": [],
        }
    )
    bull, bear = bull_bear(r, sources(), ledger, traj, health)
    assert len(bull) == 1 and "18.2%" in bull[0].text and bear == []
    assert "FACTS" in r.calls[0][2] and "Debt to equity: 0.06" in r.calls[0][2]


def test_bull_bear_cap_three_and_long_text_dropped():
    ledger, traj, health = analytics()
    many = [item(f"Point number {i} on growth.", REAL_A) for i in range(5)]
    many.append(item(" ".join(["word"] * 31), REAL_A))
    r = FakeRouter({"bull": many, "bear": [item("Financing risk via bridge loan.", REAL_B, 7)]})
    bull, bear = bull_bear(r, sources(), ledger, traj, health)
    assert len(bull) == 3 and len(bear) == 1
    assert all("word word" not in p.text for p in bull)


def test_bull_bear_llm_error_and_bad_types():
    ledger, traj, health = analytics()
    assert bull_bear(FakeRouter(LLMError("x")), sources(), ledger, traj, health) == ([], [])
    r = FakeRouter(
        {"bull": "oops", "bear": [None, {"text": 3}, item("ok text", REAL_A, 8, "NOPE")]}
    )
    assert bull_bear(r, sources(), ledger, traj, health) == ([], [])


def _facts_item(text, quote, sid="FACTS"):
    return {"text": text, "quote": quote, "source_id": sid, "page": 0}


def test_bull_facts_citation_kept_with_full_line():
    ledger, traj, health = analytics()
    r = FakeRouter({"bull": [_facts_item("Debt to equity is only 0.06 today.", "debt to equity: 0.06")], "bear": []})  # fmt: skip
    bull, _ = bull_bear(r, sources(), ledger, traj, health)
    assert len(bull) == 1
    c = bull[0].citation
    assert (c.source_id, c.page, c.quote) == ("FACTS", 0, "Debt to equity: 0.06")
    assert "source_id FACTS" in r.calls[0][1]


def test_bull_facts_quote_matching_no_line_dropped():
    ledger, traj, health = analytics()
    r = FakeRouter({"bull": [_facts_item("Margins are great and widening fast.", "Gross margin: 55%")], "bear": []})  # fmt: skip
    assert bull_bear(r, sources(), ledger, traj, health)[0] == []


def test_bull_facts_number_not_in_line_dropped():
    ledger, traj, health = analytics()
    r = FakeRouter({"bull": [_facts_item("Debt to equity is only 0.99 today.", "Debt to equity: 0.06")], "bear": []})  # fmt: skip
    assert bull_bear(r, sources(), ledger, traj, health)[0] == []


def test_snapshot_rejects_facts():
    r = FakeRouter({"summary": [_facts_item("Debt to equity is only 0.06 today.", "Debt to equity: 0.06")]})  # fmt: skip
    assert snapshot(r, sources()) is None
