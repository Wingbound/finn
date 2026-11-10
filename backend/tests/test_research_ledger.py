import json

import pytest

from finn.llm.providers import LLMError
from finn.models import Citation, Promise, Source
from finn.research.ledger import _NOT_DUE, build_ledger, compute_status, parse_horizon
from tests.fakes import FIXTURES, FakeRouter

QUARTERS = ["Q2 FY27", "Q1 FY27", "Q4 FY26", "Q3 FY26"]
REAL_T1 = "Q2 FY27 revenue stood at USD 487.6 million, registering a year-on-year growth of 20%."
REAL_T1_B = (
    "In terms of financing, we intend replacing the Euro 1.4 billion 18-month bridge loan "
    "with longer tenure, capital and favorable terms."
)
REAL_T1_C = (
    "We have received the shareholder approval for the above funding mix at the "
    "Extraordinary General Meeting held on October 5th."
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
                    "evidence_quote": REAL_T1_C,
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
    two = promise(2, "PERSISTENT-T3", "Q4 FY26")  # later: T2, T1, both shown whole
    withev = promise(3, "PERSISTENT-T3", "Q4 FY26")
    cut = promise(4, "PERSISTENT-T4", "Q3 FY26")  # later: T3, T2, T1; T2 is cut at 66,666
    table = {
        one.id: {"status": "dropped", "rationale": "Not mentioned again."},
        two.id: {"status": "dropped", "rationale": "Not mentioned again."},
        withev.id: {
            "status": "dropped",
            "evidence_quote": REAL_T1,
            "evidence_source": "PERSISTENT-T1",
            "rationale": "r",
        },
        cut.id: {"status": "dropped", "rationale": "Not mentioned again."},
    }
    led = build_ledger(FakeRouter(judge(table)), [one, two, withev, cut], sources(), {}, {})
    by = {r.promise.id: r for r in led.rows}
    assert by[one.id].status == "pending"
    assert by[two.id].status == "dropped" and by[two.id].evidence is None
    assert by[withev.id].status == "pending"
    assert by[cut.id].status == "pending"


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
    assert _kept(horizon="Q2 FY27").status == "kept"


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
    p = promise(2, "PERSISTENT-T3", "Q4 FY26")
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


# ---- I3: should_stop ----
def test_should_stop_is_checked_before_each_judge_group():
    a = promise(1, "PERSISTENT-T4", "Q3 FY26")
    b = promise(1, "PERSISTENT-T3", "Q4 FY26")
    c = promise(1, "PERSISTENT-T2", "Q1 FY27")
    r = FakeRouter({"judgements": []})
    checks = iter([False, True, True])
    notes: list[str] = []
    led = build_ledger(r, [a, b, c], sources(), {}, {}, notes=notes, should_stop=lambda: next(checks))  # fmt: skip
    assert len(r.calls) == 1
    assert all(x.status == "pending" and x.rationale == "Not assessed" for x in led.rows)
    assert notes == ["Remaining promise checks skipped: build deadline reached"]


def test_should_stop_never_blocks_rows_without_later_calls():
    r = FakeRouter({"judgements": []})
    led = build_ledger(r, [promise(1, "PERSISTENT-T1", "Q2 FY27")], sources(), {}, {}, should_stop=lambda: True)  # fmt: skip
    assert led.rows[0].rationale == "Too recent to judge" and r.calls == []


# ---- I5: the judged path's period handling ----
def test_judge_prompt_states_made_in_and_period():
    from finn.research.ledger import _user_prompt

    later = sources()[:1]
    p = promise(1, "PERSISTENT-T2", "Q1 FY27", horizon="FY27")
    assert "(made in Q1 FY27; target period FY27)" in _user_prompt([p], later)
    q = promise(2, "PERSISTENT-T2", "Q1 FY27", horizon="medium term")
    assert "(made in Q1 FY27) |" in _user_prompt([q], later)


@pytest.mark.parametrize(
    "horizon,quote",
    [
        ("by FY27", "x y z a b c d"),
        ("end of FY27", "x y z a b c d"),
        ("exit FY27", "x y z a b c d"),
        ("by March 2027", "x y z a b c d"),
        (None, "We will commission the new plant by the end of this financial year"),
        (None, "We will commission the plant by end of FY27"),
        (None, "We will exit FY 2027 with the plant running"),
        (None, "We expect the plant by mar 2027"),
        ("next year", "x y z a b c d"),
    ],
)
def test_lenient_period_scan_downgrades_kept(horizon, quote):
    row = _kept(horizon=horizon, citation=_cit(quote))  # made in Q1 FY27, newest Q2 FY27
    assert row.status == "pending" and row.rationale == "Target not yet due — tracking is not delivery"  # fmt: skip


def test_lenient_scan_this_year_in_q4_call_means_next_fy():
    from finn.research.ledger import _not_yet_due

    ev = Citation(source_id="PERSISTENT-T1", page=7, quote="x y z a b c d")
    p = promise(1, "PERSISTENT-T3", "Q4 FY26", citation=_cit("We will finish the plant this year"))  # fmt: skip
    assert _not_yet_due(p, ("kept", ev, "r"), "Q4 FY27")[0] == "kept"  # FY27 has ended
    assert _not_yet_due(p, ("kept", ev, "r"), "Q2 FY27")[0] == "pending"  # FY27, not FY26


@pytest.mark.parametrize(
    "horizon,quote",
    [
        (None, "We delivered the plant in FY26 as planned"),
        (None, "x y z a b c d"),
        ("next quarter", "x y z a b c d"),  # Q2 FY27: the newest call reports it
    ],
)
def test_past_or_no_period_stays_kept(horizon, quote):
    assert _kept(horizon=horizon, citation=_cit(quote)).status == "kept"


def test_long_horizon_is_relative_to_newest_call():
    from finn.research.ledger import _not_yet_due

    ev = Citation(source_id="PERSISTENT-T1", page=7, quote="x y z a b c d")
    far = promise(1, "PERSISTENT-T2", "Q1 FY27", horizon="FY26", citation=_cit("we did well in FY26 and target 25% by FY29"))  # fmt: skip
    assert _not_yet_due(far, ("kept", ev, "r"), "Q2 FY27")[0] == "pending"  # FY29 >= FY27 + 2
    near = far.model_copy(update={"citation": _cit("we did well in FY26 and target 25% by FY28")})
    assert _not_yet_due(near, ("kept", ev, "r"), "Q2 FY27")[0] == "kept"  # first mention FY26
    old = far.model_copy(update={"citation": _cit("we did well in FY26 and target 25% by FY30")})
    assert _not_yet_due(old, ("kept", ev, "r"), "Q2 FY29")[0] == "kept"  # FY30 < FY29 + 2


# ---- I7: credibility needs 3 resolved promises ----
def test_credibility_none_under_three_resolved():
    a = promise(1, "PERSISTENT-T4", "Q3 FY26")
    b = promise(2, "PERSISTENT-T4", "Q3 FY26")
    ev = {"evidence_quote": REAL_T1, "evidence_source": "PERSISTENT-T1"}
    table = {a.id: dict(status="kept", rationale="ok", **ev), b.id: dict(status="missed", rationale="no", **ev)}  # fmt: skip
    led = build_ledger(FakeRouter(judge(table)), [a, b], sources(), {}, {})
    assert led.counts["kept"] == 1 and led.counts["missed"] == 1
    assert led.credibility_pct is None


# ---- minors ----
def test_judge_prompt_missed_rule():
    from finn.research.ledger import SYSTEM

    assert (
        "missed only if management cut, lowered or moved the target, or the stated time passed "
        "without it" in " ".join(SYSTEM.split())
    )


def _big(i, quarter):
    return Source(id=f"B{i}", kind="transcript", title=f"{quarter} call", quarter=quarter, url="u", pages=["word " * 2_000] * 30)  # fmt: skip


def test_truncated_evidence_is_flagged_and_blocks_dropped():
    from finn.research.ledger import _user_prompt

    srcs = [_big(1, "Q2 FY27"), _big(2, "Q1 FY27"), _big(3, "Q4 FY26")]
    p = promise(1, "B3", "Q4 FY26")
    user = _user_prompt([p], [srcs[1], srcs[0]])  # oldest first, as build_ledger passes them
    assert "TRUNCATED (later pages not shown): B2, B1." in user
    led = build_ledger(FakeRouter(judge({p.id: {"status": "dropped", "rationale": "r"}})), [p], srcs, {}, {})  # fmt: skip
    assert led.rows[0].status == "pending"


def test_untruncated_evidence_has_no_flag():
    from finn.research.ledger import _user_prompt

    p = promise(2, "PERSISTENT-T3", "Q4 FY26")
    assert "TRUNCATED" not in _user_prompt([p], [sources()[1], sources()[0]])
    q = promise(3, "PERSISTENT-T4", "Q3 FY26")
    later = [sources()[2], sources()[1], sources()[0]]
    assert "TRUNCATED (later pages not shown): PERSISTENT-T2." in _user_prompt([q], later)


def test_no_transcripts_note():
    led = build_ledger(FakeRouter({"judgements": []}), [], [], {}, {})
    assert led.note == "Not enough concall transcripts on file (found 0)" and led.rows == []


@pytest.mark.parametrize(
    "quote,status",
    [
        ("We expect to reach this by 2030", "pending"),
        ("Revenue of Rs 2075 crore was delivered", "kept"),
        ("Order inflow was ₹2060 cr in the quarter", "kept"),
        ("We shipped 2080 units in the quarter", "kept"),
    ],
)
def test_bare_years_but_not_amounts_are_long(quote, status):
    from finn.research.ledger import _not_yet_due

    ev = Citation(source_id="PERSISTENT-T1", page=7, quote="x y z a b c d")
    p = promise(1, "PERSISTENT-T2", "Q1 FY27", citation=_cit(quote))
    assert _not_yet_due(p, ("kept", ev, "r"), "Q2 FY27")[0] == status


# ---- deterministic verdict guards (period / restated / below target) ----
_PERIOD_MSG = "The later quote is about a different period"
_RESTATED_MSG = "The later call restated the target; delivery is not shown yet"


def _guarded(ev, status="kept", quote="x y z a b c d", stats=None, **kw):
    src = [
        Source(id="G-T1", kind="transcript", title="a", quarter="Q3 FY26", url="u", pages=["p"]),
        Source(
            id="G-T2",
            kind="transcript",
            title="b",
            quarter="Q2 FY27",
            url="u",
            pages=[f"Opening remarks. {ev} Thank you."],
        ),
    ]
    p = promise(1, "G-T1", "Q3 FY26", **kw)
    p = p.model_copy(update={"citation": Citation(source_id="G-T1", page=1, quote=quote)})
    j = {"status": status, "evidence_quote": ev, "evidence_source": "G-T2", "rationale": "r"}
    return build_ledger(FakeRouter(judge({p.id: j})), [p], src, {}, {}, stats=stats).rows[0]


def test_guard_dixon_restated_target_is_pending():
    ev = "The plant is nearing completion, and we expect the operation to commence by Q2 this fiscal."
    stats: dict = {}
    row = _guarded(ev, horizon="Q2 FY27", stats=stats)
    assert row.status == "pending" and row.evidence is None and row.rationale == _RESTATED_MSG
    assert stats["verdicts_downgraded"]["restated"] == 1


def test_guard_idea_below_target_is_pending():
    ev = "For the quarter was Rs. 17.5 billion and for H1FY26 at Rs. 42 billion."
    stats: dict = {}
    row = _guarded(
        ev,
        quote="That range of INR 50 billion to INR 60 billion, which we had indicated for H1",
        kind="quantitative",
        target_low=50,
        target_high=60,
        unit="usd_bn",
        stats=stats,
    )
    assert row.status == "pending" and row.evidence is None
    assert row.rationale == "The later figure (42) is below the target (50–60)"
    assert stats["verdicts_downgraded"]["below_target"] == 1


def test_guard_indigo_other_period_is_pending():
    ev = "June quarter's capacity growth came in at 3% on a year-over-year basis."
    stats: dict = {}
    row = _guarded(ev, status="missed", horizon="Q4 FY26", stats=stats)
    assert row.status == "pending" and row.evidence is None and row.rationale == _PERIOD_MSG
    assert stats["verdicts_downgraded"]["other_period"] == 1


@pytest.mark.parametrize(
    "ev,status,horizon,kw",
    [
        (
            (
                "June quarter's capacity growth came in at 3% on a year-over-year basis, "
                "broadly in line with our guidance."
            ),
            "kept",
            "Q1FY27",
            {},
        ),
        (
            "Effective tax rate for FY26 stood at 22.6%.",
            "kept",
            "FY26",
            {"kind": "quantitative", "target_low": 20, "target_high": 24, "unit": "%"},
        ),
        ("This marks our 26th sequential quarter of revenue growth.", "kept", None, {}),
        ("Capacity growth in Q1 FY27 came in at 3% year over year.", "missed", "Q1 FY27", {}),
        (
            "We commissioned the plant in Q2 and will ramp up in Q3 of this year.",
            "kept",
            "Q2 FY27",
            {},
        ),
    ],
)
def test_guard_leaves_valid_verdicts(ev, status, horizon, kw):
    stats: dict = {}
    row = _guarded(ev, status=status, horizon=horizon, stats=stats, **kw)
    assert row.status == status and row.evidence is not None
    assert not any(stats["verdicts_downgraded"].values())


def test_guard_lower_is_better_skips_below_target():
    row = _guarded(
        "Net debt stood at 1,850 crore at the end of the period.",
        quote="We will bring net debt below 2,000 crore",
        kind="quantitative",
        target_low=2000,
        unit="cr",
    )
    assert row.status == "kept"


def test_guard_fy_horizon_other_fy_downgrades_and_quarter_only_passes():
    assert _guarded("Margin for FY25 stood at 22 percent overall.", horizon="FY26").status == (
        "pending"
    )
    assert _guarded("Margin in Q2 stood at 22 percent overall.", horizon="FY26").status == "kept"
    # FY inside a quarter mention is not an FY mention
    assert _guarded("Margin for Q2 FY25 stood at 22 percent.", horizon="FY26").status == "kept"


def test_guard_stats_count_each_reason():
    stats: dict = {}
    _guarded("We expect the plant to commence by Q2 this fiscal.", horizon="Q2 FY27", stats=stats)
    _guarded("We expect the plant to commence by Q2 this fiscal.", horizon="Q2 FY27", stats=stats)
    assert stats["verdicts_downgraded"] == {
        "other_period": 0,
        "restated": 2,
        "below_target": 0,
        "other_measure": 0,
        "meets_target": 0,
    }


def test_guard_fused_period_label_is_not_a_number():
    row = _guarded(
        "Capex in H1FY26 we spent Rs 42 billion in total.",
        quote="That range of INR 50 billion to INR 60 billion, which we had indicated",
        kind="quantitative",
        target_low=50,
        target_high=60,
        unit="usd_bn",
    )
    assert row.status == "pending" and "(42)" in row.rationale
    row = _guarded(
        "Capex in Q3 FY'26 we spent Rs 42 billion in total.",
        quote="That range of INR 50 billion to INR 60 billion, which we had indicated",
        kind="quantitative",
        target_low=50,
        target_high=60,
        unit="usd_bn",
    )
    assert row.status == "pending" and "(42)" in row.rationale


def test_guard_present_tense_number_is_delivery():
    ev = "Margin is 21% and we expect 22% next year."
    assert _guarded(ev, horizon="FY26").status == "kept"


def test_guard_dixon_still_downgrades_with_present_tense_rule():
    ev = "The plant is nearing completion, and we expect the operation to commence by Q2 this fiscal."
    assert _guarded(ev, horizon="Q2 FY27").status == "pending"


def test_guard_weak_delivery_cue_before_intention_is_restated():
    ev = "We had planned to commission by Q3 and will now do so in Q4."
    row = _guarded(ev, horizon="Q3 FY26")
    assert row.status == "pending" and row.rationale == _RESTATED_MSG


# ---- Plan 6 audit of 16 new dossiers: five more mechanical verdict errors ----


def test_guard_passive_future_is_not_delivery():  # MAXHEALTH
    ev = "100 beds at Max Lucknow : in the existing 468-bed facility will be commissioned over the next 2 quarters."
    assert _guarded(ev, horizon="next two quarters").rationale == _RESTATED_MSG


def test_guard_should_and_a_bare_was_do_not_make_delivery():  # CGPOWER
    ev = "although our original plan was 2027 financial -- '27, '28 financial year, but I think we should do it at least 1 year before."
    assert _guarded(ev, horizon="2028").rationale == _RESTATED_MSG


def test_guard_is_set_for_is_future():  # PREMIERENE
    ev = "Our 5.6 gigawatt module line is set for completion in March 2026, 4.8 gigawatt cell line in June 2026."
    assert _guarded(ev, horizon="September 2026").rationale == _RESTATED_MSG


def test_guard_a_past_figure_is_still_delivery():
    ev = "Revenue was up 18% for the year and we will keep investing in brands."
    assert _guarded(ev, horizon="FY26").status == "kept"


def test_guard_evidence_measuring_something_else_is_pending():  # ULTRACEMCO
    q = "So, we should have approximately 8 to 9 million tons more coming in this quarter."
    ev = "During the quarter, we also added 116 megawatts of renewable power, 10 megawatt of waste heat recovery."
    row = _guarded(ev, quote=q, horizon="this quarter")
    assert row.status == "pending" and row.rationale == "The later quote measures something else"


def test_guard_same_measure_stays_resolved():  # CGPOWER 65,000 MVA
    q = "And in the next 1 quarter or so, we'll be 65,000 MVA."
    ev = "the power transformer is already about 75,000 MVA and distribution is about close to 10,000 MVA."
    assert _guarded(ev, quote=q, horizon="next 1 quarter").status == "kept"


def test_guard_missed_with_a_figure_that_meets_the_target_is_pending():  # ZYDUSLIFE
    q = "We will still track at 23% plus margin in the Quarter 4."
    ev = "our operating profitability remained robust with an EBITDA margin of 24% despite continued investments."
    row = _guarded(
        ev, status="missed", quote=q, horizon="Q4", kind="quantitative", target_low=23.0, unit="%"
    )
    assert (
        row.status == "pending"
        and row.rationale == "The later figure (24%) meets the target (at least 23%)"
    )


def test_guard_missed_below_target_stays_missed():
    q = "We will still track at 23% plus margin in the Quarter 4."
    ev = "our operating profitability came in with an EBITDA margin of 21% this quarter."
    assert (
        _guarded(
            ev,
            status="missed",
            quote=q,
            horizon="Q4",
            kind="quantitative",
            target_low=23.0,
            unit="%",
        ).status
        == "missed"
    )


# ---- Plan 6 final review I6/I7: the restated check, both ways ----


@pytest.mark.parametrize(
    "ev",
    [
        "EBITDA margin improved to 24.5% in Q2 due to better product mix.",
        "Revenue increased 18% due to strong volume growth.",
        "The new capacity came on stream as scheduled.",
        "We added 300 beds this year and should add 200 more next year.",
        "Revenue rose 21% year-on-year, and we should do better in the second half.",
        "We were able to complete the 5 GW line, and production will ramp up next quarter.",
    ],
)
def test_guard_delivered_sentences_stay_kept(ev):
    assert _guarded(ev, horizon=None).status == "kept", ev


@pytest.mark.parametrize(
    "ev",
    [
        "The balance 140 beds will also be commissioned post Diwali.",
        "The second line will now be completed in Q4.",
        "The plant should hopefully be commissioned by March.",
        "The new block is expected to be fully commissioned in Q3.",
    ],
)
def test_guard_an_adverb_after_the_modal_is_still_a_restatement(ev):
    assert _guarded(ev, horizon=None).rationale == _RESTATED_MSG, ev


def test_an_annual_target_judged_mid_year_is_not_yet_due():  # LODHA, Plan 6 review fix pass
    q = "Our commitment of 20% PAT growth is an annual guidance, not a quarterly one."
    ev = (
        "We expect to easily beat our profit guidance of 20% growth. In the first half, having already "
        "touched INR 2,400 crores, we feel very confident of being able to beat this guidance."
    )
    src = [
        Source(id="G-T1", kind="transcript", title="a", quarter="Q1 FY27", url="u", pages=["p"]),
        Source(
            id="G-T2",
            kind="transcript",
            title="b",
            quarter="Q2 FY27",
            url="u",
            pages=[f"Opening. {ev} Thanks."],
        ),
    ]
    p = promise(1, "G-T1", "Q1 FY27", horizon="annual")
    p = p.model_copy(update={"citation": Citation(source_id="G-T1", page=1, quote=q)})
    j = {"status": "kept", "evidence_quote": ev, "evidence_source": "G-T2", "rationale": "r"}
    row = build_ledger(FakeRouter(judge({p.id: j})), [p], src, {}, {}).rows[0]
    assert row.status == "pending" and row.rationale == _NOT_DUE
