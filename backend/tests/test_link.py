"""Plan 6: a results card meets the promises on the company's calls."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from finn import db
from finn.models import (
    IST,
    Citation,
    Dossier,
    Ledger,
    LedgerRow,
    MarginRow,
    MetricRow,
    Promise,
    ResultsCard,
    Source,
)
from finn.research.link import attach_promises, pace_note, promise_notes


def card(
    fmt: str = "indas",
    revenue_yoy: float = 21.6,
    pat_yoy: float = 16.2,
    margin: float | None = 16.1,
):
    metrics = [
        MetricRow(key="revenue", label="Revenue", value=1000.0, qoq_pct=6.0, yoy_pct=revenue_yoy),
        MetricRow(key="pat", label="PAT", value=100.0, qoq_pct=4.7, yoy_pct=pat_yoy),
    ]
    margins = (
        []
        if margin is None
        else [MarginRow(key="ebitda_margin", label="EBITDA margin", value_pct=margin)]
    )
    return ResultsCard(
        symbol="ABC",
        period_end=date(2026, 9, 30),
        period_label="Q2 FY27",
        basis="consolidated",
        format=fmt,
        audited=False,
        compared_qoq=date(2026, 6, 30),
        compared_yoy=date(2025, 9, 30),
        metrics=metrics,
        margins=margins,
        notes=[],
        sources=[],
    )


SOURCES = [
    Source(
        id="T1",
        kind="transcript",
        title="Q2 FY27 earnings call (Oct 2026)",
        quarter="Q2 FY27",
        url="u1",
        pages=[],
    ),
    Source(
        id="T2",
        kind="transcript",
        title="Q1 FY27 earnings call (Aug 2026)",
        quarter="Q1 FY27",
        url="u2",
        pages=[],
    ),
]


def row(
    quote: str,
    *,
    metric: str | None = "revenue_growth",
    lo: float | None = 15.0,
    hi: float | None = 18.0,
    unit: str | None = "%",
    horizon: str | None = "FY27",
    made_in: str = "Q1 FY27",
    status: str = "pending",
    n: int = 1,
) -> LedgerRow:
    sid = "T1" if made_in == "Q2 FY27" else "T2"
    return LedgerRow(
        promise=Promise(
            id=f"{sid}-{n}",
            citation=Citation(source_id=sid, page=4, quote=quote),
            topic="growth",
            kind="quantitative" if lo is not None else "qualitative",
            metric=metric,
            target_low=lo,
            target_high=hi,
            unit=unit,
            horizon=horizon,
            made_in=made_in,
        ),
        status=status,
        method="judged",
        rationale="r",
    )


def dossier(rows: list[LedgerRow], symbol: str = "ABC") -> Dossier:
    return Dossier(
        symbol=symbol,
        name="Abc Ltd",
        basis="consolidated",
        built_at=datetime(2026, 11, 9, tzinfo=IST),
        sources=SOURCES,
        ledger=Ledger(rows=rows, counts={}, credibility_pct=None),
        snapshot=None,
        trajectory=None,
        health=None,
        bull=[],
        bear=[],
        notes=[],
        cost={},
        build_seconds=1.0,
    )


REVENUE_FY27 = "We expect revenue to grow 15% to 18% in FY27, led by the new plant."


def test_pace_fires_when_the_quote_names_the_line_for_this_fiscal_year():
    p = pace_note(row(REVENUE_FY27).promise, card())
    assert p is not None
    assert (p.line, p.actual, p.word) == ("Revenue", 21.6, "above")
    assert p.basis == "YoY growth in Q2 FY27"


@pytest.mark.parametrize(
    ("quote", "kw"),
    [
        ("We are confident of 20% to 24% AUM growth in FY27.", {}),  # AUM is not revenue
        ("We expect PRASK to grow by more than 25 percent in FY27.", {}),  # not revenue either
        (
            "We expect revenue growth of 15% to 18% in constant currency in FY27.",
            {},
        ),  # mismatch cue
        ("The segment revenue should grow 15% to 18% in FY27.", {}),  # segment
        ("We expect revenue to grow 15% to 18% over the long term.", {"horizon": "long term"}),
        ("We expect revenue to grow 15% to 18% in FY29.", {"horizon": "FY29"}),  # another year
        ("We expect revenue to grow 15% to 18% in FY27.", {"unit": "cr"}),  # not a percentage
        (
            "EBIT margin should be 16% to 17% in FY27.",
            {"metric": "ebitda_margin", "lo": 16.0, "hi": 17.0},
        ),
    ],
)
def test_no_pace_when_a_gate_fails(quote, kw):
    assert pace_note(row(quote, **kw).promise, card()) is None


def test_margin_pace_and_its_absence_for_a_lender():
    quote = "We expect EBITDA margin of 15% to 17% for FY27."
    p = pace_note(row(quote, metric="ebitda_margin", lo=15.0, hi=17.0).promise, card())
    assert p is not None and (p.line, p.actual, p.word) == ("EBITDA margin", 16.1, "within")
    assert (
        pace_note(
            row(quote, metric="ebitda_margin", lo=15.0, hi=17.0).promise, card("bank", margin=None)
        )
        is None
    )


def test_open_ended_target_says_at_or_above():
    quote = "We expect PAT to grow at least 12% in FY27."
    p = pace_note(row(quote, metric="pat_growth", lo=12.0, hi=None).promise, card())
    assert p is not None and p.word == "at or above"
    p = pace_note(row(quote, metric="pat_growth", lo=20.0, hi=None).promise, card())
    assert p is not None and p.word == "below"


def test_notes_are_open_promises_ranked_this_year_first():
    rows = [
        row("Resolved one.", status="kept", n=1),
        row("Long-term aspiration of 30% growth.", horizon="long term", n=2, metric="other"),
        row(
            "Something qualitative about plants.",
            lo=None,
            hi=None,
            unit=None,
            horizon=None,
            metric=None,
            n=3,
            made_in="Q2 FY27",
        ),
        row(REVENUE_FY27, n=4),
    ]
    notes = promise_notes(dossier(rows), card())
    assert [nt.quote for nt in notes] == [
        REVENUE_FY27,
        "Something qualitative about plants.",
        "Long-term aspiration of 30% growth.",
    ]
    assert notes[0].call == "Q1 FY27 call, p. 4"
    assert notes[0].target == "15–18%"
    assert notes[0].pace is not None
    assert all("Resolved" not in nt.quote for nt in notes)


def test_notes_are_capped():
    rows = [row(f"Promise number {i} about growth.", n=i, metric="other") for i in range(6)]
    assert len(promise_notes(dossier(rows), card())) == 3


def _story(symbol: str, category: str = "results"):
    from finn.models import Classification, Filing, ScoredFiling, Story

    f = Filing(
        seq_id="1",
        symbol=symbol,
        company="Abc",
        nse_desc="d",
        subject="s",
        filed_at=datetime(2026, 11, 7, tzinfo=IST),
    )
    sf = ScoredFiling(
        filing=f,
        cls=Classification(category=category, by="rules", confidence=1.0),
        score=90,
        tier="critical",
        reasons=[],
    )
    return Story(
        id=f"{symbol}:{category}:1",
        symbol=symbol,
        company="Abc",
        category=category,
        score=90,
        tier="critical",
        headline=sf,
        members=[sf],
        latest_at=f.filed_at,
        results=card(),
    )


def test_attach_promises_to_results_stories_only(tmp_path):
    conn = db.connect(tmp_path / "x.sqlite")
    db.init_db(conn)
    db.save_dossier(conn, dossier([row(REVENUE_FY27)]))
    with_dossier, without, other = _story("ABC"), _story("NOPE"), _story("ABC", "mna")
    attach_promises(conn, [with_dossier, without, other])
    assert len(with_dossier.promises) == 1 and with_dossier.promises[0].pace is not None
    assert without.promises == [] and other.promises == []


def test_the_digest_carries_promises_on_results_stories(tmp_path, monkeypatch):
    """On the committed snapshot: BAJFINANCE reported this week and has a dossier."""
    import shutil
    from datetime import timedelta
    from pathlib import Path

    from fastapi.testclient import TestClient

    from finn.api import main as api_main
    from finn.api.deps import get_conn, get_now
    from finn.portfolio import load_portfolio

    path = tmp_path / "seed.sqlite"
    shutil.copyfile(Path(__file__).resolve().parent.parent / "seed" / "finn.sqlite", path)
    c = db.connect(path)
    db.init_db(c)
    now = db.latest_filed_at(c, [h.symbol for h in load_portfolio()]) + timedelta(hours=2)
    c.close()

    def conn():
        cc = db.connect(path)
        try:
            yield cc
        finally:
            cc.close()

    api_main.app.dependency_overrides[get_conn] = conn
    api_main.app.dependency_overrides[get_now] = lambda: now
    try:
        body = (
            TestClient(api_main.app)
            .post("/digest", json={"hours": 24 * 30, "floor": "everything"})
            .json()
        )
    finally:
        api_main.app.dependency_overrides.clear()
    bajaj = [
        s
        for s in body["stories"]
        if s["symbol"] == "BAJFINANCE" and s["category"] == "results" and s["results"]
    ]
    assert bajaj and bajaj[0]["promises"], (
        "BAJFINANCE's results story should carry its open promises"
    )
    others = [s for s in body["stories"] if s["category"] != "results"]
    assert all(s["promises"] == [] for s in others)


@pytest.mark.parametrize(
    ("quote", "kw", "shown"),
    [
        (
            "Between 26%, 27% growth we should deliver on a full year basis.",
            {"lo": 26.0, "hi": 27.0},
            "26–27%",
        ),
        (
            "We will deliver 180-odd applications and 600-odd agents.",
            {"lo": 180.0, "hi": 600.0, "unit": None},
            None,
        ),
        (
            "A net new deal adding about $125 million a year.",
            {"lo": 650.0, "hi": None, "unit": "usd_mn"},
            None,
        ),
        (
            "We expect USD 25 to 30 million over two quarters.",
            {"lo": 25.0, "hi": 30.0, "unit": "usd_mn"},
            "$25–30 mn",
        ),
    ],
)
def test_a_target_is_shown_only_when_its_numbers_are_in_the_quote(quote, kw, shown):
    notes = promise_notes(dossier([row(quote, metric="other", **kw)]), card())
    assert notes[0].target == shown
