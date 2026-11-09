import json

import pytest

from finn.llm.providers import LLMError
from finn.models import Citation, Promise, Source
from finn.research.ledger import build_ledger, compute_status, parse_horizon
from tests.fakes import FIXTURES, FakeRouter

QUARTERS = ["Q2 FY27", "Q1 FY27", "Q4 FY26", "Q3 FY26"]
REAL_T1 = "Q2 FY27 revenue stood at USD 487.6 million, registering a year-on-year growth of 20%."
REAL_T1_B = (
    "In terms of financing, we intend replacing the Euro 1.4 billion 18-month bridge loan "
    "with longer tenure, capital and favorable terms."
)


def sources() -> list[Source]:
    data = json.loads((FIXTURES / "research" / "PERSISTENT_transcripts.json").read_text())
    return [
        Source(
            id=f"PERSISTENT-T{i + 1}",
            kind="transcript",
            title=f"{q} call",
            quarter=q,
            url=d["url"],
            pages=d["pages"],
        )
        for i, (d, q) in enumerate(zip(data, QUARTERS, strict=True))
    ]


def promise(n, src, made_in, **kw):
    d = {
        "id": f"{src}-{n}",
        "citation": Citation(source_id=src, page=1, quote="x y z a b c d"),
        "topic": "financing bridge loan",
        "kind": "qualitative",
        "made_in": made_in,
    }
    d.update(kw)
    return Promise(**d)


def judge(table):
    """Reply callable: returns the judgements for the ids appearing in the user prompt."""

    def reply(task, system, user):
        return {"judgements": [dict(id=i, **j) for i, j in table.items() if i in user]}

    return reply


# ---- parse_horizon ----
@pytest.mark.parametrize(
    "h,made,want",
    [
        ("Q3 FY27", "Q1 FY27", ("quarter", "Q3 FY27")),
        ("Q3FY27", "Q1 FY27", ("quarter", "Q3 FY27")),
        ("FY27", "Q1 FY27", ("fy", "FY27")),
        ("FY2027", "Q1 FY27", ("fy", "FY27")),
        ("FY 27", "Q1 FY27", ("fy", "FY27")),
        ("fiscal 2027", "Q1 FY27", ("fy", "FY27")),
        ("next quarter", "Q2 FY27", ("quarter", "Q3 FY27")),
        ("coming quarter", "Q4 FY26", ("quarter", "Q1 FY27")),
        ("this year", "Q4 FY26", ("fy", "FY26")),
        ("current year", "Q1 FY27", ("fy", "FY27")),
        ("this fiscal", "Q2 FY27", ("fy", "FY27")),
        ("next year", "Q4 FY26", ("fy", "FY27")),
        ("next fiscal", "Q2 FY27", ("fy", "FY28")),
        ("medium term", "Q2 FY27", None),
        ("H2", "Q2 FY27", None),
        ("next 2-3 years", "Q2 FY27", None),
        (None, "Q2 FY27", None),
        ("next quarter", "", None),
        ("H2 FY27", "Q1 FY27", None),
        ("H1 FY27", "Q1 FY27", None),
        ("exit FY27", "Q1 FY27", None),
        ("by end of FY27", "Q1 FY27", None),
        ("FY27-28", "Q1 FY27", None),
        ("FY27 to FY28", "Q1 FY27", None),
        ("end of this year", "Q1 FY27", None),
        ("in FY27", "Q1 FY27", ("fy", "FY27")),
        ("for Q3 FY27", "Q1 FY27", ("quarter", "Q3 FY27")),
        ("fiscal year 2027", "Q1 FY27", ("fy", "FY27")),
        ("Q3 FY2027", "Q1 FY27", ("quarter", "Q3 FY27")),
        ("this financial year", "Q1 FY27", ("fy", "FY27")),
    ],
)
def test_parse_horizon(h, made, want):
    assert parse_horizon(h, made) == want


# ---- compute_status ----
MAR = {"Mar 2026": {"Sales": 400.0, "Operating Profit": 80.0, "Net Profit": 40.0}}  # Mar FY-end
LENDER = {"Mar 2026": {"Revenue": 400.0, "Financing Profit": 80.0, "Net Profit": 40.0}}
_SAYS = {
    "revenue_growth": "revenue to grow",
    "pat_growth": "net profit to grow",
    "ebitda_margin": "EBITDA margin of",
}


def qtab(cur, prev):
    return {"Sep 2026": cur, "Sep 2025": prev}


def p_growth(
    lo, metric="revenue_growth", unit="%", horizon="Q2 FY27", quote=None, made_in="Q1 FY27", hi=None
):
    """A quantitative promise whose quote names the metric and the horizon, as C1 requires."""
    q = quote or f"We expect {_SAYS.get(metric, 'capex of')} {lo:g}% in {horizon}"
    return promise(
        1,
        "PERSISTENT-T2",
        made_in,
        kind="quantitative",
        metric=metric,
        target_low=lo,
        target_high=hi,
        unit=unit,
        horizon=horizon,
        citation=Citation(source_id="PERSISTENT-T2", page=1, quote=q),
    )


@pytest.mark.parametrize(
    "lo,status",
    [(15, "kept"), (18, "kept"), (22, "partly"), (25, "missed")],
)
def test_compute_growth(lo, status):
    q = qtab({"Sales": 118.0}, {"Sales": 100.0})  # +18%
    s, a = compute_status(p_growth(lo), q, MAR)
    assert s == status
    assert a.value == pytest.approx(18.0) and a.unit == "%" and a.period == "Q2 FY27"


def test_compute_growth_lender_and_pat():
    q = {
        "Sep 2026": {"Revenue": 110.0, "Net Profit": 30.0},
        "Sep 2025": {"Revenue": 100.0, "Net Profit": 20.0},
    }
    assert compute_status(p_growth(10), q, LENDER)[0] == "kept"
    s, a = compute_status(p_growth(40, metric="pat_growth"), q, LENDER)
    assert s == "kept" and a.value == pytest.approx(50.0)


def test_compute_fy_growth_uses_annual():
    a = {"Mar 2027": {"Sales": 130.0}, "Mar 2026": {"Sales": 100.0}}
    s, act = compute_status(p_growth(25, horizon="FY27"), {}, a)
    assert s == "kept" and act.period == "FY27"


@pytest.mark.parametrize("lo,status", [(20, "kept"), (21, "partly"), (21.5, "missed")])
def test_compute_margin(lo, status):
    q = {"Sep 2026": {"Sales": 200.0, "Operating Profit": 40.0}}  # 20%
    p = p_growth(lo, metric="ebitda_margin")
    s, a = compute_status(p, q, MAR)
    assert s == status and a.value == pytest.approx(20.0)


def test_lender_margin_is_judged_not_computed():
    q = {"Sep 2026": {"Revenue": 200.0, "Financing Profit": 100.0}}
    assert compute_status(p_growth(45, metric="ebitda_margin"), q, LENDER) is None
    # the same table for a non-lender P&L would compute
    assert compute_status(p_growth(45, metric="ebitda_margin", quote="We expect EBITDA margin of 45% in Q2 FY27"), {"Sep 2026": {"Sales": 200.0, "Operating Profit": 100.0}}, MAR)[0] == "kept"  # fmt: skip


def test_compute_pending_when_period_missing():
    q = {"Jun 2026": {"Sales": 1.0}}
    assert compute_status(p_growth(15), q, MAR) == ("pending", None)
    assert compute_status(p_growth(15, horizon="FY28"), q, MAR) == ("pending", None)


def test_compute_none_cases():
    q = qtab({"Sales": 118.0}, {"Sales": 100.0})
    assert compute_status(p_growth(15), q, MAR) is not None  # control
    assert compute_status(p_growth(15, unit="cr"), q, MAR) is None
    assert compute_status(p_growth(15, metric="capex"), q, MAR) is None
    assert compute_status(p_growth(15, horizon="medium term"), q, MAR) is None
    assert compute_status(promise(1, "PERSISTENT-T2", "Q1 FY27"), q, MAR) is None


# ---- build_ledger ----
def test_computed_row_and_rationale():
    p = p_growth(15)
    q = {"Sep 2026": {"Sales": 118.2}, "Sep 2025": {"Sales": 100.0}}
    r = FakeRouter({"judgements": []})
    led = build_ledger(r, [p], sources(), q, MAR)
    row = led.rows[0]
    assert row.method == "computed" and row.status == "kept" and row.actual.value == 18.2
    assert row.rationale == "Revenue grew 18.2% YoY in Q2 FY27 against a target of at least 15%"
    assert r.calls == []


def test_judged_kept_with_page_corrected():
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    r = FakeRouter(
        judge(
            {
                p.id: {
                    "status": "kept",
                    "evidence_quote": REAL_T1_B,
                    "evidence_source": "PERSISTENT-T1",
                    "evidence_page": 20,
                    "rationale": "Bridge loan refinancing is being replaced as said.",
                }
            }
        )
    )
    row = build_ledger(r, [p], sources(), {}, {}).rows[0]
    assert row.status == "kept" and row.method == "judged"
    assert row.evidence.source_id == "PERSISTENT-T1" and row.evidence.page == 7
    t = r.calls[0][2]
    assert "=== PERSISTENT-T1: Q2 FY27 call ===" in t and "PERSISTENT-T3" not in t


def test_judged_invented_quote_pending():
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    j = {
        "status": "kept",
        "evidence_quote": "Management confirmed the bridge loan was fully repaid ahead of schedule.",
        "evidence_source": "PERSISTENT-T1",
        "evidence_page": 7,
        "rationale": "Repaid.",
    }
    row = build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]
    assert row.status == "pending" and row.evidence is None
    assert row.rationale == "No verifiable later evidence"


def test_evidence_from_non_later_source_rejected():
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    j = {
        "status": "kept",
        "evidence_quote": REAL_T1,
        "evidence_source": "PERSISTENT-T3",
        "rationale": "x",
    }
    row = build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]
    assert row.status == "pending" and row.rationale == "No verifiable later evidence"


def test_dropped_needs_two_later_sources_and_no_evidence():
    one = promise(1, "PERSISTENT-T2", "Q1 FY27")  # later: T1 only
    two = promise(2, "PERSISTENT-T4", "Q3 FY26")  # later: T3, T2, T1
    withev = promise(3, "PERSISTENT-T4", "Q3 FY26")
    table = {
        one.id: {"status": "dropped", "rationale": "Not mentioned again."},
        two.id: {"status": "dropped", "rationale": "Not mentioned again."},
        withev.id: {
            "status": "dropped",
            "evidence_quote": REAL_T1,
            "evidence_source": "PERSISTENT-T1",
            "rationale": "r",
        },
    }
    led = build_ledger(FakeRouter(judge(table)), [one, two, withev], sources(), {}, {})
    by = {r.promise.id: r for r in led.rows}
    assert by[one.id].status == "pending"
    assert by[two.id].status == "dropped" and by[two.id].evidence is None
    assert by[withev.id].status == "pending"


def test_newest_source_pending_no_llm_call():
    p = promise(1, "PERSISTENT-T1", "Q2 FY27")
    r = FakeRouter({"judgements": []})
    row = build_ledger(r, [p], sources(), {}, {}).rows[0]
    assert row.status == "pending" and row.rationale == "Too recent to judge" and r.calls == []


def test_counts_credibility_order_and_call_budget():
    a = promise(1, "PERSISTENT-T4", "Q3 FY26")
    b = promise(2, "PERSISTENT-T4", "Q3 FY26")
    c = promise(1, "PERSISTENT-T3", "Q4 FY26")
    d = promise(1, "PERSISTENT-T2", "Q1 FY27")
    e = promise(1, "PERSISTENT-T1", "Q2 FY27")
    ev = {"evidence_quote": REAL_T1, "evidence_source": "PERSISTENT-T1"}
    table = {
        a.id: dict(status="kept", rationale="ok", **ev),
        b.id: dict(status="partly", rationale="some", **ev),
        c.id: dict(status="missed", rationale="no", **ev),
        d.id: dict(status="kept", rationale="ok", **ev),
    }
    r = FakeRouter(judge(table))
    led = build_ledger(r, [e, d, c, b, a], sources(), {}, {})
    assert [x.promise.id for x in led.rows] == [a.id, b.id, c.id, d.id, e.id]
    assert led.counts == {"kept": 2, "partly": 1, "missed": 1, "pending": 1, "dropped": 0}
    assert led.credibility_pct == pytest.approx((2 + 0.5) / 4 * 100)
    assert led.note is None
    assert len(r.calls) == 3 and all(c[0] == "reason" for c in r.calls)


def test_credibility_none_when_nothing_resolved():
    led = build_ledger(
        FakeRouter({"judgements": []}), [promise(1, "PERSISTENT-T2", "Q1 FY27")], sources(), {}, {}
    )
    assert led.credibility_pct is None
    assert led.rows[0].status == "pending" and led.rows[0].rationale == "Not assessed"


def test_single_source_note():
    led = build_ledger(
        FakeRouter({"judgements": []}),
        [promise(1, "PERSISTENT-T1", "Q2 FY27")],
        sources()[:1],
        {},
        {},
    )
    assert led.note == "Not enough concall transcripts on file (found 1)"
    assert len(led.rows) == 1


def test_llm_error_and_bad_reply_do_not_crash():
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    for rep in (LLMError("down"), {"judgements": "oops"}, {"judgements": [1, {"id": 5}]}):
        row = build_ledger(FakeRouter(rep), [p], sources(), {}, {}).rows[0]
        assert row.status == "pending" and row.rationale == "Not assessed"


def test_unknown_status_becomes_pending_with_code_rationale():
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    long = " ".join(f"w{i}" for i in range(50))
    j = {"status": "great", "rationale": long}
    row = build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]
    assert row.status == "pending"
    assert row.rationale == "No later evidence of the outcome yet"


def test_nonpositive_target_is_judged_not_computed():
    p = p_growth(-5)
    q = qtab({"Sales": 118.0}, {"Sales": 100.0})
    assert compute_status(p, q, MAR) is None
    r = FakeRouter({"judgements": []})
    row = build_ledger(r, [p], sources(), q, MAR).rows[0]
    assert row.method == "judged" and len(r.calls) == 1


def test_missing_row_labels_is_judged_not_pending_computed():
    q = {"Sep 2026": {"Other": 1.0}, "Sep 2025": {"Other": 1.0}}
    assert compute_status(p_growth(15), q, MAR) is None
    assert compute_status(p_growth(15, metric="ebitda_margin"), q, MAR) is None


def test_later_key_uses_source_quarter_over_made_in():
    # made_in claims Q3 FY26 but the source is T2 (Q1 FY27): only T1 is later.
    p = promise(1, "PERSISTENT-T2", "Q3 FY26")
    r = FakeRouter({"judgements": []})
    build_ledger(r, [p], sources(), {}, {})
    u = r.calls[0][2]
    assert "=== PERSISTENT-T1:" in u and "PERSISTENT-T2:" not in u and "PERSISTENT-T3:" not in u


def test_ids_order_numerically():
    ps = [promise(10, "PERSISTENT-T1", "Q2 FY27"), promise(2, "PERSISTENT-T1", "Q2 FY27")]
    rows = build_ledger(FakeRouter({"judgements": []}), ps, sources(), {}, {}).rows
    assert [r.promise.id for r in rows] == ["PERSISTENT-T1-2", "PERSISTENT-T1-10"]


def test_judge_prompt_includes_whole_later_transcript():
    late = "deal, let's say the intangibles are up like $ 100 odd million, and you did"
    assert late in sources()[0].pages[16]  # T1 page 17
    p = promise(1, "PERSISTENT-T4", "Q3 FY26")
    r = FakeRouter({"judgements": []})
    build_ledger(r, [p], sources(), {}, {})
    system, user = r.calls[0][1], r.calls[0][2]
    assert late in user
    assert "=== PERSISTENT-T1:" in user and "Prefer the most recent mention" in system


def test_system_prompt_reaffirming_rules():
    from finn.research.ledger import SYSTEM

    assert (
        "Restating, reaffirming or repeating the same target is NOT evidence of delivery: use pending."
        in SYSTEM
    )
    assert "The evidence quote must show the outcome, not the promise being repeated." in SYSTEM


@pytest.mark.parametrize(
    "status,has_ev", [("pending", False), ("kept", True), ("partly", True), ("missed", True)]
)
def test_pending_rows_carry_no_evidence(status, has_ev):
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    j = {
        "status": status,
        "evidence_quote": REAL_T1,
        "evidence_source": "PERSISTENT-T1",
        "rationale": "r",
    }
    row = build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]
    assert row.status == status and (row.evidence is not None) == has_ev


def test_judge_evidence_total_budget():
    from finn.research.ledger import JUDGE_EVIDENCE_CHARS, _user_prompt

    later = [
        Source(
            id=f"S{i}", kind="transcript", title="t", quarter="Q1 FY27", url="u",
            pages=["x" * 9_000] * 30,
        )
        for i in range(3)
    ]  # fmt: skip
    p = promise(1, "PERSISTENT-T4", "Q3 FY26")
    user = _user_prompt([p], later)
    for s in later:
        block = user.split(f"=== {s.id}: t ===\n")[1].split("\n\n=== ")[0]
        assert len(block) <= JUDGE_EVIDENCE_CHARS // 3 == 66_666
    assert len(user) <= JUDGE_EVIDENCE_CHARS + 2_000


def test_segment_promise_judged_not_computed():
    q = {"Sep 2026": {"Sales": 100.0, "Operating Profit": 20.0}}
    seg = promise(
        1, "PERSISTENT-T2", "Q1 FY27", kind="quantitative", metric="ebitda_margin",
        target_low=15, unit="%", horizon="Q2 FY27",
        citation=Citation(source_id="PERSISTENT-T2", page=1, quote="we expect segment EBITDA margin of 15% in Q2 FY27"),
    )  # fmt: skip
    row = build_ledger(FakeRouter({"judgements": []}), [seg], sources(), q, MAR).rows[0]
    assert row.method == "judged"
    plain = seg.model_copy(
        update={
            "citation": seg.citation.model_copy(
                update={"quote": "we expect EBITDA margin of 15% in Q2 FY27"}
            )
        }
    )
    assert build_ledger(FakeRouter({"judgements": []}), [plain], sources(), q, MAR).rows[0].method == "computed"  # fmt: skip


def _kept(status="kept", **kw):
    p = promise(1, "PERSISTENT-T2", "Q1 FY27", **kw)
    j = {"status": status, "evidence_quote": REAL_T1, "evidence_source": "PERSISTENT-T1", "rationale": "r"}  # fmt: skip
    return build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]


def _cit(q):
    return Citation(source_id="PERSISTENT-T2", page=1, quote=q)


@pytest.mark.parametrize(
    "q", ["we target a margin of 25% by FY30", "our long-term margin goal is 25%"]
)
def test_long_horizon_kept_becomes_pending(q):
    row = _kept(citation=_cit(q))
    assert row.status == "pending" and row.evidence is None
    assert row.rationale == "Target not yet due — tracking is not delivery"
    assert _kept("partly", citation=_cit(q)).status == "pending"


def test_long_horizon_missed_stays_missed():
    assert _kept("missed", citation=_cit("we target a margin of 25% by FY30")).status == "missed"


def test_future_horizon_pending_past_horizon_kept():
    assert _kept(horizon="Q3 FY27").status == "pending"
    assert _kept(horizon="Q1 FY27").status == "kept"


def test_same_metric_period_sentence():
    from finn.research.ledger import SYSTEM

    assert "The evidence must concern the same metric and the same period as the promise; a number for a different quarter or year is not evidence for this promise." in SYSTEM  # fmt: skip


# ---- C1: gates on the computed path ----
_ROW = {"Sales": 118.0, "Operating Profit": 23.6, "Net Profit": 12.0}
_PREV = {"Sales": 100.0, "Operating Profit": 20.0, "Net Profit": 10.0}
GQ = {"Jun 2025": _PREV, "Sep 2025": _PREV, "Jun 2026": _ROW, "Sep 2026": _ROW}
GA = {"Mar 2025": _PREV, "Mar 2026": _ROW, "Mar 2027": {"Sales": 139.24, "Operating Profit": 27.0, "Net Profit": 14.0}}  # fmt: skip


def graded(p, quarters=GQ, annual=GA):
    return compute_status(p, quarters, annual)


@pytest.mark.parametrize(
    "horizon,made_in",
    [("Q2 FY27", "Q2 FY27"), ("Q1 FY27", "Q2 FY27"), ("FY27", "Q4 FY27"), ("FY26", "Q1 FY27")],
)
def test_gate_period_must_end_after_the_call(horizon, made_in):
    assert graded(p_growth(15, horizon=horizon, made_in=made_in)) is None
    assert graded(p_growth(15, horizon=horizon, made_in="Q4 FY25")) is not None  # control


@pytest.mark.parametrize(
    "phrase",
    ["this year", "current year", "this fiscal", "this financial year", "next year", "next fiscal",
     "next financial year"],
)  # fmt: skip
def test_gate_relative_year_in_q4_call(phrase):
    q = f"We expect revenue to grow 15% {phrase}"
    assert graded(p_growth(15, horizon=phrase, quote=q, made_in="Q4 FY26")) is None
    assert graded(p_growth(15, horizon=phrase, quote=q, made_in="Q3 FY26")) is not None


@pytest.mark.parametrize(
    "horizon,quote",
    [
        ("FY27", "We expect revenue to grow 15% next year"),
        ("Q2 FY27", "We expect revenue to grow 15% in Q3 FY27"),
        ("next year", "We expect revenue to grow 15% in FY27"),
        ("FY27", "We expect revenue to grow 15% in Q3 FY27"),
        ("FY27", "We expect revenue to grow 15% over FY27-28"),
    ],
)
def test_gate_horizon_must_be_in_quote(horizon, quote):
    assert graded(p_growth(15, horizon=horizon, quote=quote)) is None


@pytest.mark.parametrize(
    "horizon,quote",
    [
        ("FY27", "We expect revenue to grow 15% in FY 27"),
        ("FY27", "We expect revenue to grow 15% in FY2027"),
        ("FY 2027", "We expect revenue to grow 15% in FY27"),
        ("FY27", "We expect revenue to grow 15% in fiscal 2027"),
        ("Q2 FY27", "We expect revenue to grow 15% in Q2FY27"),
        ("Q2FY27", "We expect revenue to grow 15% in Q2 FY 27"),
    ],
)
def test_gate_horizon_label_forms_match(horizon, quote):
    assert graded(p_growth(15, horizon=horizon, quote=quote)) is not None


@pytest.mark.parametrize(
    "metric,quote",
    [
        ("revenue_growth", "We expect to grow 15% in Q2 FY27"),
        ("revenue_growth", "We expect the business to grow 15% in Q2 FY27"),
        ("pat_growth", "We expect revenue to grow 15% in Q2 FY27"),
        ("pat_growth", "We expect patent income to grow 15% in Q2 FY27"),
        ("ebitda_margin", "We expect margin of 15% in Q2 FY27"),
        ("ebitda_margin", "We expect gross margin of 15% in Q2 FY27"),
    ],
)
def test_gate_quote_must_name_the_metric(metric, quote):
    assert graded(p_growth(15, metric=metric, quote=quote)) is None


@pytest.mark.parametrize(
    "metric,quote",
    [
        ("revenue_growth", "We expect sales to grow 15% in Q2 FY27"),
        ("revenue_growth", "We expect top line to grow 15% in Q2 FY27"),
        ("revenue_growth", "We expect topline to grow 15% in Q2 FY27"),
        ("revenue_growth", "We expect turnover to grow 15% in Q2 FY27"),
        ("revenue_growth", "We expect revenues to grow 15% in Q2 FY27"),
        ("pat_growth", "We expect PAT to grow 15% in Q2 FY27"),
        ("pat_growth", "We expect profit after tax to grow 15% in Q2 FY27"),
        ("ebitda_margin", "We expect operating margin of 15% in Q2 FY27"),
        ("ebitda_margin", "We expect OPM of 15% in Q2 FY27"),
        ("ebitda_margin", "We expect EBITDA margins of 15% in Q2 FY27"),
    ],
)
def test_gate_metric_words_accepted(metric, quote):
    assert graded(p_growth(15, metric=metric, quote=quote)) is not None


@pytest.mark.parametrize(
    "metric,quote",
    [
        ("ebitda_margin", "We expect operating margin of 15% at the EBIT level in Q2 FY27"),
        ("revenue_growth", "We expect revenue to grow 15% QoQ in Q2 FY27"),
        ("revenue_growth", "We expect revenue to grow 15% quarter-on-quarter in Q2 FY27"),
        ("revenue_growth", "We expect revenue to grow 15% quarter on quarter in Q2 FY27"),
        ("revenue_growth", "We expect revenue to grow 15% sequentially in Q2 FY27"),
        ("revenue_growth", "We expect a revenue CQGR of 15% in Q2 FY27"),
        ("revenue_growth", "We expect revenue to grow 15% in constant currency in Q2 FY27"),
        ("revenue_growth", "We expect revenue to grow 15% in dollar terms in Q2 FY27"),
        ("revenue_growth", "We expect USD revenue to grow 15% in Q2 FY27"),
        ("revenue_growth", "We expect revenue to grow 15% to US$ 500 million in Q2 FY27"),
        ("revenue_growth", "We expect revenue to grow 15% to $500 million in Q2 FY27"),
        ("ebitda_margin", "We expect EBITDA margin of 15% in Q2 FY27, up 200 bps"),
        ("ebitda_margin", "We expect EBITDA margin of 15% in Q2 FY27, up 200 basis points"),
        ("ebitda_margin", "We expect EBITDA margin expansion to 15% in Q2 FY27"),
        ("ebitda_margin", "We expect EBITDA margin to improve to 15% in Q2 FY27"),
        ("ebitda_margin", "We expect EBITDA margin to rise by 2% in Q2 FY27"),
    ],
)
def test_gate_metric_mismatch_cues(metric, quote):
    assert graded(p_growth(15, metric=metric, quote=quote)) is None


def test_gate_ebitda_is_not_ebit():
    assert graded(p_growth(15, metric="ebitda_margin")) is not None


def test_gate_lender_margin():
    q = {"Sep 2026": {"Revenue": 200.0, "Financing Profit": 100.0}}
    assert graded(p_growth(45, metric="ebitda_margin"), q, LENDER) is None
    s, _ = graded(p_growth(15), {"Sep 2026": {"Revenue": 118.0}, "Sep 2025": {"Revenue": 100.0}}, LENDER)  # fmt: skip
    assert s == "kept"  # lender revenue growth still computes


@pytest.mark.parametrize(
    "annual",
    [
        {"Dec 2024": _PREV, "Dec 2025": _ROW, "TTM": _ROW},
        {"TTM": _ROW},
        {},
    ],
)
def test_gate_fiscal_year_must_end_in_march(annual):
    assert graded(p_growth(15), GQ, annual) is None
    assert graded(p_growth(15), GQ, {**GA, "TTM": _ROW}) is not None  # TTM is ignored


def test_probe_cases_are_judged():
    """The reviewer's probe1 cases: each was confidently computed before C1."""
    annual = {
        "Mar 2025": {"Sales": 100.0, "Operating Profit": 20.0, "Net Profit": 10.0},
        "Mar 2026": {"Sales": 118.0, "Operating Profit": 24.0, "Net Profit": 12.0},
    }
    quarters = {"Sep 2025": {"Sales": 25.0, "Operating Profit": 5.0, "Net Profit": 2.5},
                "Jun 2026": {"Sales": 29.0, "Operating Profit": 6.0, "Net Profit": 3.0},
                "Sep 2026": {"Sales": 30.0, "Operating Profit": 6.3, "Net Profit": 3.0}}  # fmt: skip
    cases = [
        ("We expect revenue to grow 15% this quarter on strong demand", "revenue_growth", 15, "Q2 FY27", "Q2 FY27"),
        ("We expect revenue to grow 15% this year with new launches", "revenue_growth", 15, "this year", "Q4 FY26"),
        ("We will expand EBIT margin to 18% in FY26 driven by utilisation", "ebitda_margin", 18, "FY26", "Q1 FY26"),
        ("We will improve our margins by 2% in FY26 through cost actions", "ebitda_margin", 2, "FY26", "Q1 FY26"),
        ("We expect to grow 3% quarter on quarter in Q2 FY27 in dollar terms", "revenue_growth", 3, "Q2 FY27", "Q1 FY27"),
    ]  # fmt: skip
    for quote, metric, lo, hz, made in cases:
        p = p_growth(lo, metric=metric, horizon=hz, quote=quote, made_in=made)
        assert compute_status(p, quarters, annual) is None, quote


def test_computed_rationale_for_range():
    q = {"Sep 2026": {"Sales": 118.2, "Operating Profit": 23.64}, "Sep 2025": {"Sales": 100.0}}
    p = p_growth(15, hi=18, quote="We expect revenue to grow 15-18% in Q2 FY27")
    row = build_ledger(FakeRouter({"judgements": []}), [p], sources(), q, MAR).rows[0]
    assert row.rationale == "Revenue grew 18.2% YoY in Q2 FY27 against a target of 15–18%"
    m = p_growth(15, hi=18, metric="ebitda_margin", quote="We expect EBITDA margin of 15-18% in Q2 FY27")  # fmt: skip
    row = build_ledger(FakeRouter({"judgements": []}), [m], sources(), q, MAR).rows[0]
    assert row.rationale == "EBITDA margin was 20.0% in Q2 FY27 against a target of 15–18%"


# ---- I1: the judge rationale is grounded ----
def _resolved(rationale, status="kept"):
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    j = {"status": status, "evidence_quote": REAL_T1, "evidence_source": "PERSISTENT-T1", "rationale": rationale}  # fmt: skip
    return build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]


def test_resolved_rationale_with_ungrounded_number_becomes_template():
    row = _resolved("Revenue grew 22% to USD 640 million, beating the 18% guidance.")
    assert row.status == "kept" and row.rationale == "See the later evidence quote."
    assert _resolved("It fell 9% short.", "missed").rationale == "See the later evidence quote."


def test_resolved_rationale_grounded_and_short_is_kept():
    row = _resolved("Revenue grew 20% year on year to USD 487.6 million in Q2 FY27.")
    assert row.rationale == "Revenue grew 20% year on year to USD 487.6 million in Q2 FY27."
    assert _resolved("Delivered.", "partly").rationale == "Delivered."


def test_resolved_rationale_over_30_words_becomes_template():
    long = " ".join(["delivered"] * 31)
    assert _resolved(long).rationale == "See the later evidence quote."
    assert _resolved("   ").rationale == "See the later evidence quote."


def test_pending_rationale_is_a_code_string():
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    j = {"status": "pending", "evidence_quote": "", "rationale": "Management cut the target to 9% and delayed the plant to FY29."}  # fmt: skip
    row = build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]
    assert row.status == "pending" and row.rationale == "No later evidence of the outcome yet"


def test_dropped_rationale_is_a_code_string():
    p = promise(2, "PERSISTENT-T4", "Q3 FY26")
    j = {"status": "dropped", "rationale": "They went quiet after the 12% miss."}
    row = build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]
    assert row.status == "dropped" and row.rationale == "Not mentioned in the later calls"


# ---- I2: judge failures are reported ----
@pytest.mark.parametrize("rep", [LLMError("down"), {"judgements": "oops"}, ["not", "a", "dict"]])
def test_judge_failure_is_noted(rep):
    notes: list[str] = []
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    led = build_ledger(FakeRouter(rep), [p], sources(), {}, {}, notes=notes)
    assert led.rows[0].status == "pending" and led.rows[0].rationale == "Not assessed"
    assert notes == ["Some promises could not be judged (model unavailable)"]


def test_judge_success_adds_no_note():
    notes: list[str] = []
    build_ledger(FakeRouter({"judgements": []}), [promise(1, "PERSISTENT-T2", "Q1 FY27")], sources(), {}, {}, notes=notes)  # fmt: skip
    assert notes == []
