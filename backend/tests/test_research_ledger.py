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
def qtab(cur, prev):
    return {"Sep 2026": cur, "Sep 2025": prev}


def p_growth(lo, metric="revenue_growth", unit="%", horizon="Q2 FY27"):
    return promise(
        1,
        "PERSISTENT-T2",
        "Q1 FY27",
        kind="quantitative",
        metric=metric,
        target_low=lo,
        unit=unit,
        horizon=horizon,
    )


@pytest.mark.parametrize(
    "lo,status",
    [(15, "kept"), (18, "kept"), (22, "partly"), (25, "missed")],
)
def test_compute_growth(lo, status):
    q = qtab({"Sales": 118.0}, {"Sales": 100.0})  # +18%
    s, a = compute_status(p_growth(lo), q, {})
    assert s == status
    assert a.value == pytest.approx(18.0) and a.unit == "%" and a.period == "Q2 FY27"


def test_compute_growth_lender_and_pat():
    q = {
        "Sep 2026": {"Revenue": 110.0, "Net Profit": 30.0},
        "Sep 2025": {"Revenue": 100.0, "Net Profit": 20.0},
    }
    assert compute_status(p_growth(10), q, {})[0] == "kept"
    s, a = compute_status(p_growth(40, metric="pat_growth"), q, {})
    assert s == "kept" and a.value == pytest.approx(50.0)


def test_compute_fy_growth_uses_annual():
    a = {"Mar 2027": {"Sales": 130.0}, "Mar 2026": {"Sales": 100.0}}
    s, act = compute_status(p_growth(25, horizon="FY27"), {}, a)
    assert s == "kept" and act.period == "FY27"


@pytest.mark.parametrize("lo,status", [(20, "kept"), (21, "partly"), (21.5, "missed")])
def test_compute_margin(lo, status):
    q = {"Sep 2026": {"Sales": 200.0, "Operating Profit": 40.0}}  # 20%
    p = p_growth(lo, metric="ebitda_margin")
    s, a = compute_status(p, q, {})
    assert s == status and a.value == pytest.approx(20.0)


def test_compute_margin_lender():
    q = {"Sep 2026": {"Revenue": 200.0, "Financing Profit": 100.0}}
    assert compute_status(p_growth(45, metric="ebitda_margin"), q, {})[0] == "kept"


def test_compute_pending_when_period_missing():
    q = {"Jun 2026": {"Sales": 1.0}}
    assert compute_status(p_growth(15), q, {}) == ("pending", None)
    assert compute_status(p_growth(15, horizon="FY28"), q, {}) == ("pending", None)


def test_compute_none_cases():
    q = qtab({"Sales": 118.0}, {"Sales": 100.0})
    assert compute_status(p_growth(15, unit="cr"), q, {}) is None
    assert compute_status(p_growth(15, metric="capex"), q, {}) is None
    assert compute_status(p_growth(15, horizon="medium term"), q, {}) is None
    assert compute_status(promise(1, "PERSISTENT-T2", "Q1 FY27"), q, {}) is None


# ---- build_ledger ----
def test_computed_row_and_rationale():
    p = p_growth(15)
    q = {"Sep 2026": {"Sales": 118.2}, "Sep 2025": {"Sales": 100.0}}
    r = FakeRouter({"judgements": []})
    led = build_ledger(r, [p], sources(), q, {})
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


def test_unknown_status_and_rationale_truncated():
    p = promise(1, "PERSISTENT-T2", "Q1 FY27")
    long = " ".join(f"w{i}" for i in range(50))
    j = {"status": "great", "rationale": long}
    row = build_ledger(FakeRouter(judge({p.id: j})), [p], sources(), {}, {}).rows[0]
    assert row.status == "pending"
    assert len(row.rationale.split()) == 30 and row.rationale.endswith("…")


def test_nonpositive_target_is_judged_not_computed():
    p = p_growth(-5)
    q = qtab({"Sales": 118.0}, {"Sales": 100.0})
    assert compute_status(p, q, {}) is None
    r = FakeRouter({"judgements": []})
    row = build_ledger(r, [p], sources(), q, {}).rows[0]
    assert row.method == "judged" and len(r.calls) == 1


def test_missing_row_labels_is_judged_not_pending_computed():
    q = {"Sep 2026": {"Other": 1.0}, "Sep 2025": {"Other": 1.0}}
    assert compute_status(p_growth(15), q, {}) is None
    assert compute_status(p_growth(15, metric="ebitda_margin"), q, {}) is None


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
