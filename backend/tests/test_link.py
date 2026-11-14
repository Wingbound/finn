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
    higher = "We expect PAT to grow at least 20% in FY27."  # the target must be in the quote (I1)
    p = pace_note(row(higher, metric="pat_growth", lo=20.0, hi=None).promise, card())
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
    rows = [
        row(f"Promise number {i} about growth.", n=i, metric="other", lo=float(10 + i))
        for i in range(6)
    ]
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


def test_a_dossier_carries_the_latest_filed_quarter(tmp_path):
    """BAJFINANCE has a results card in the snapshot; a dossier-only symbol gets null."""
    import shutil
    from pathlib import Path

    from fastapi.testclient import TestClient

    from finn.api import main as api_main
    from finn.api.deps import get_conn

    path = tmp_path / "seed.sqlite"
    shutil.copyfile(Path(__file__).resolve().parent.parent / "seed" / "finn.sqlite", path)

    def conn():
        cc = db.connect(path)
        try:
            yield cc
        finally:
            cc.close()

    api_main.app.dependency_overrides[get_conn] = conn
    try:
        client = TestClient(api_main.app)
        bajaj = client.get("/research/BAJFINANCE").json()
        indigo = client.get("/research/INDIGO").json()
    finally:
        api_main.app.dependency_overrides.clear()
    assert bajaj["latest_results"]["period_label"].startswith("Q")
    assert bajaj["latest_results"]["format"] == "nbfc"
    assert indigo["latest_results"] is None


def test_a_target_needs_its_unit_in_the_quote():  # VOLTAS: "18 months" is not "18x"
    q = "So 18 months from now is when we are expecting full-fledged commercial production of the compressors."
    notes = promise_notes(
        dossier([row(q, metric="other", lo=18.0, hi=None, unit="x", horizon="18 months")]), card()
    )
    assert notes[0].target is None


def test_an_open_ended_target_reads_at_least():  # ZYDUSLIFE: "24% plus"
    q = "We are on track to deliver a 24% plus EBITDA margin in line with our FY27 expectations."
    notes = promise_notes(dossier([row(q, metric="ebitda_margin", lo=24.0, hi=None)]), card())
    assert notes[0].target == "at least 24%"


def test_the_same_guidance_twice_is_shown_once():  # ZYDUSLIFE pages 5 and 11
    a = row(
        "We are on track to deliver a 24% plus EBITDA margin in FY27.",
        metric="ebitda_margin",
        lo=24.0,
        hi=None,
        n=1,
    )
    b = row(
        "Yes, we maintain that guidance of 24% EBITDA margin for the full year.",
        metric="ebitda_margin",
        lo=24.0,
        hi=None,
        n=2,
    )
    c = row(
        "Capex of 1,500 to 1,600 crores this year.",
        metric="capex",
        lo=1500.0,
        hi=1600.0,
        unit="cr",
        n=3,
    )
    notes = promise_notes(dossier([a, b, c]), card())
    assert [n.quote[:10] for n in notes] == ["We are on ", "Capex of 1"]


def test_at_least_only_when_the_words_are_beside_the_number():  # TATASTEEL
    q = "We intend to increase the same in FY2027 to around Rs 20,000 crores of which more than 60% will be spent in India."
    notes = promise_notes(dossier([row(q, metric="capex", lo=20000.0, hi=None, unit="cr")]), card())
    assert notes[0].target == "₹20,000 cr"
    q2 = "Capex will be more than Rs 1,500 crores this year."
    assert (
        promise_notes(dossier([row(q2, metric="capex", lo=1500.0, hi=None, unit="cr")]), card())[
            0
        ].target
        == "at least ₹1,500 cr"
    )


# ---- Plan 6 final review ----


@pytest.mark.parametrize(
    ("quote", "kw"),
    [
        (
            "We expect double-digit revenue growth in FY27.",
            {"lo": 10.0, "hi": None},
        ),  # I1: 10 not in quote
        ("We expect mid-teens revenue growth in FY27.", {"lo": 15.0, "hi": None}),
        (
            "We expect PAT margin of 12% in FY27.",
            {"metric": "pat_growth", "lo": 12.0, "hi": None},
        ),  # I2
        (
            "We expect net profit margin of 12% for FY27.",
            {"metric": "pat_growth", "lo": 12.0, "hi": None},
        ),
        ("We expect sales volume growth of 15 to 18% in FY27.", {}),
        ("Same-store sales growth of 15 to 18% in FY27.", {}),
        ("We expect export sales to grow 15 to 18% in FY27.", {}),
        ("Domestic formulation sales should grow 15 to 18% in FY27.", {}),
        ("Organic revenue growth, excluding the acquisition, should be 15 to 18% in FY27.", {}),
        ("Passenger revenue per available seat kilometre to grow 15 to 18% in FY27.", {}),
        ("Unit revenue should grow 15 to 18% in FY27.", {}),
        ("We expect AUM growth of 15 to 18% in FY27, and revenue growth should track it.", {}),
        ("We expect operating margin of 15 to 18% in FY27.", {"metric": "ebitda_margin"}),
        (
            "Presales of 200 billion with an embedded EBITDA margin of approximately 15% in FY27.",
            {"metric": "ebitda_margin", "lo": 15.0, "hi": None},
        ),
        ("We expect H2 revenue growth of 15 to 18%.", {}),  # period not in the quote
        ("We expect revenue to grow 15 to 18% for FY28.", {}),  # horizon mislabelled FY27
    ],
)
def test_no_pace_for_neighbouring_measures(quote, kw):
    assert pace_note(row(quote, **kw).promise, card()) is None, quote


def test_a_q4_calls_this_year_is_not_this_card(tmp_path):  # I3
    q = "This year we expect revenue to grow 15 to 18%."
    c4 = card().model_copy(update={"period_label": "Q4 FY26"})
    p = row(q, horizon="this year", made_in="Q4 FY26").promise
    assert pace_note(p, c4) is None


def test_point_targets_are_not_floors():  # I1: "at or above" only for open targets
    q = "We expect EBITDA margin of 16% for FY27."
    p = pace_note(row(q, metric="ebitda_margin", lo=16.0, hi=None).promise, card())
    assert p is not None and p.word == "above" and p.scope == "year"


@pytest.mark.parametrize(
    ("horizon", "made_in", "label"),
    [
        ("FY27", "Q1 FY27", "FY27"),
        ("next quarter", "Q1 FY27", "Q2 FY27"),
        ("this quarter", "Q1 FY27", "was due Q1 FY27"),
        ("Q4 FY26", "Q3 FY26", "was due Q4 FY26"),
        ("next year", "Q4 FY26", '"next year", said on the Q4 FY26 call'),
        ("next nine months", "Q1 FY27", '"next nine months", said on the Q1 FY27 call'),
        (None, "Q1 FY27", None),
    ],
)
def test_horizons_read_correctly_on_a_later_card(horizon, made_in, label):  # I4
    q = "We will add capacity in this period."
    notes = promise_notes(
        dossier(
            [row(q, metric="other", lo=None, hi=None, unit=None, horizon=horizon, made_in=made_in)]
        ),
        card(),
    )
    assert notes[0].horizon_label == label


def test_a_cut_is_not_a_target():  # I5, TVSMOTOR
    q = "Next year, the investments will be much lower. It will be maybe another INR500 crores, INR600 crores lower than this INR 2,400 crores."
    notes = promise_notes(
        dossier(
            [
                row(
                    q,
                    metric="capex",
                    lo=500.0,
                    hi=600.0,
                    unit="cr",
                    horizon="next year",
                    made_in="Q4 FY26",
                )
            ]
        ),
        card(),
    )
    assert notes[0].target is None


@pytest.mark.parametrize(
    ("metric", "kind"),
    [("revenue_growth", "target"), ("capex", "guided"), ("other", "figure"), (None, "figure")],
)
def test_only_results_lines_are_called_targets(metric, kind):  # I5
    q = "We expect revenue to grow 15% to 18% in FY27."
    notes = promise_notes(dossier([row(q, metric=metric)]), card())
    assert notes[0].target_kind == kind


def test_far_targets_rank_after_near_ones():  # M2
    far = row(
        "Revenue of 15% to 18% growth by FY30 is our aspiration.",
        horizon="FY30",
        n=1,
        made_in="Q2 FY27",
    )
    near = row(
        "We will open two plants this year.",
        lo=None,
        hi=None,
        unit=None,
        metric=None,
        horizon="this year",
        n=2,
    )
    notes = promise_notes(dossier([far, near]), card())
    assert notes[0].quote.startswith("We will open")


def test_dedupe_keeps_the_copy_with_a_pace_note():  # M3
    a = row(
        "We are confident of 15% to 18% revenue growth.", n=1, made_in="Q2 FY27"
    )  # no period in the quote
    b = row("We expect revenue to grow 15% to 18% in FY27.", n=2, made_in="Q1 FY27")
    notes = promise_notes(dossier([a, b]), card())
    assert len(notes) == 1 and notes[0].pace is not None


def test_a_quarter_target_says_so():  # M4
    q = "We expect revenue to grow 15% to 18% in Q2 FY27."
    p = pace_note(row(q, horizon="Q2 FY27").promise, card())
    assert p is not None and p.scope == "quarter"


def test_a_corrupt_dossier_gives_no_notes(tmp_path):  # M5
    conn = db.connect(tmp_path / "x.sqlite")
    db.init_db(conn)
    conn.execute(
        "INSERT INTO dossiers (symbol, built_at, payload_json) VALUES ('ABC', '2026-11-09', '{not json')"
    )
    conn.commit()
    st = _story("ABC")
    attach_promises(conn, [st])
    assert st.promises == []


# Plan 8: a results card shows the company's own promises, not one about another listed company
TECHM_QUOTE = (
    "We will come out with the next phase for Tech Mahindra as we close this phase that we "
    "talked about, which is by end of FY27 we get to 15% EBIT margin."
)


def test_a_promise_about_another_company_is_left_off_the_card():
    rows = [row(TECHM_QUOTE, metric="other", lo=15.0, hi=None, n=1), row(REVENUE_FY27, n=2)]
    notes = promise_notes(dossier(rows, symbol="M&M"), card(), others={"tech mahindra"})
    assert [nt.quote for nt in notes] == [REVENUE_FY27]


def test_a_quote_naming_the_company_itself_stays():
    own = "Mahindra & Mahindra will grow revenue 15% to 18% in FY27."
    notes = promise_notes(dossier([row(own)], symbol="M&M"), card(), others={"tech mahindra"})
    assert [nt.quote for nt in notes] == [own]


def test_attach_promises_skips_promises_naming_another_known_company(tmp_path):
    conn = db.connect(tmp_path / "x.sqlite")
    db.init_db(conn)
    rows = [row(TECHM_QUOTE, metric="other", lo=15.0, hi=None, n=1), row(REVENUE_FY27, n=2)]
    mm = dossier(rows, symbol="M&M").model_copy(update={"name": "Mahindra & Mahindra Ltd"})
    db.save_dossier(conn, mm)
    st = _story("M&M")
    attach_promises(conn, [st])
    assert [nt.quote for nt in st.promises] == [REVENUE_FY27]


def test_on_the_snapshot_mm_card_does_not_quote_tech_mahindra():
    import sqlite3
    from pathlib import Path

    from finn.digest import card_or_none
    from finn.research.link import company_names, other_names

    seed = Path(__file__).resolve().parent.parent / "seed" / "finn.sqlite"
    conn = sqlite3.connect(f"{seed.as_uri()}?mode=ro&immutable=1", uri=True)  # no -wal files
    conn.row_factory = sqlite3.Row
    try:
        d = db.get_dossier(conn, "M&M")
        found = card_or_none(conn, "M&M")
        assert d is not None and found is not None
        others = other_names(company_names(conn), "M&M")
        assert "tech mahindra" in others and not any("mahindra & mahindra" in n for n in others)
        quotes = [nt.quote.casefold() for nt in promise_notes(d, found[0], others=others)]
        assert quotes and not any("tech mahindra" in q for q in quotes)
    finally:
        conn.close()


def test_a_name_is_never_cut_down_to_a_common_word(tmp_path):
    # Final review: "Coal India Ltd" must not become "coal", or a live COALINDIA build would
    # hide every promise that mentions coal on another company's card.
    from finn.research.link import company_names

    conn = db.connect(tmp_path / "x.sqlite")
    db.init_db(conn)
    for sym, name in [
        ("COALINDIA", "Coal India Ltd"),
        ("DIXON", "Dixon Technologies (India) Ltd"),
        ("POLYCAB", "Polycab India Ltd"),
    ]:
        db.save_dossier(conn, dossier([], symbol=sym).model_copy(update={"name": name}))
    names = company_names(conn)
    assert names["COALINDIA"] == {"coal india"}
    assert "dixon technologies" in names["DIXON"]
    assert "polycab india" in names["POLYCAB"] and "polycab" not in names["POLYCAB"]


def test_a_corrupt_dossier_row_does_not_take_the_digest_down(tmp_path):
    # Final review: json_extract over a malformed payload raised and 500'd /digest
    conn = db.connect(tmp_path / "x.sqlite")
    db.init_db(conn)
    db.save_dossier(conn, dossier([row(REVENUE_FY27)]))
    conn.execute(
        "INSERT INTO dossiers (symbol, built_at, payload_json) VALUES ('BAD', '2026-11-09', '{not json')"
    )
    conn.commit()
    st = _story("ABC")
    attach_promises(conn, [st])
    assert [nt.quote for nt in st.promises] == [REVENUE_FY27]
