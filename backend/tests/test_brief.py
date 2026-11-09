from datetime import datetime

from finn import db
from finn.digest import build_digest
from finn.enrich.brief import enrich_briefs, make_brief
from finn.llm.providers import LLMError
from finn.models import IST, Classification, Filing
from tests.fakes import FakeNSE, FakeRouter

URL = "https://nsearchives.nseindia.com/corporate/acq.pdf"
WHEN = datetime(2026, 11, 5, 10, 0, tzinfo=IST)
SINCE = datetime(2026, 11, 1, tzinfo=IST)
TEXT = (
    "The Board approved the acquisition of 100% of Alpha Ltd for a consideration of "
    "₹1,250 crore. Completion is expected in 6 months."
)
SUMMARY = "Company to acquire Alpha Limited. Further details are in the filing."


def _filing(seq="A1", summary=SUMMARY, pdf_url=URL, at=WHEN) -> Filing:
    return Filing(
        seq_id=seq,
        symbol="ACME",
        company="Acme Limited",
        nse_desc="Acquisition",
        subject="Acquisition of Alpha Ltd",
        nse_summary=summary,
        pdf_url=pdf_url,
        filed_at=at,
    )


def _seed(conn, f, category="mna", noise=False):
    db.upsert_filings(conn, [f])
    db.save_classifications(
        conn,
        {f.seq_id: Classification(category=category, by="rules", confidence=1.0, noise=noise)},
    )
    if f.pdf_url:
        db.save_doc_text(conn, f.pdf_url, TEXT)


def _reply(one_liner="Acme buys Alpha Ltd for ₹1,250 crore.", facts=None, quote=None):
    return {"one_liner": one_liner, "facts": facts or [], "quote": quote}


def test_grounded_brief_kept():
    b = make_brief(FakeRouter(_reply()), _filing(), TEXT)
    assert b.by == "llm" and "1,250" in b.one_liner and b.source_seq_id == "A1"


def test_invented_number_falls_back_to_summary():
    b = make_brief(FakeRouter(_reply("Acme pays ₹9,999 crore.")), _filing(), TEXT)
    assert b.by == "nse_summary"
    assert b.one_liner == "Company to acquire Alpha Limited."


def test_long_summary_fallback_cut_to_40_words():
    long = " ".join(["word"] * 60) + "."
    b = make_brief(FakeRouter(_reply("Acme pays ₹9,999 crore.")), _filing(summary=long), TEXT)
    assert b.one_liner.endswith("…") and len(b.one_liner.rstrip("…").split()) == 40


def test_too_long_one_liner_rejected():
    b = make_brief(FakeRouter(_reply(" ".join(["word"] * 31))), _filing(), TEXT)
    assert b.by == "nse_summary"


def test_ungrounded_fact_dropped_grounded_fact_kept():
    facts = [
        {"label": "Consideration", "value": "₹1,250 crore"},
        {"label": "Stake", "value": "75%"},
        {"label": "Target", "value": "Alpha Ltd"},
        {"label": "Bad", "value": 5},
    ]
    b = make_brief(FakeRouter(_reply(facts=facts)), _filing(), TEXT)
    assert [f.label for f in b.facts] == ["Consideration", "Target"]


def test_fact_without_digit_must_be_in_source():
    facts = [{"label": "Buyer", "value": "Zeta Corp"}]
    b = make_brief(FakeRouter(_reply(facts=facts)), _filing(), TEXT)
    assert b.facts == []


def test_facts_capped_at_three():
    facts = [{"label": f"L{i}", "value": "100%"} for i in range(5)]
    assert len(make_brief(FakeRouter(_reply(facts=facts)), _filing(), TEXT).facts) == 3


def test_quote_not_in_source_dropped():
    b = make_brief(FakeRouter(_reply(quote="Board rejected the deal")), _filing(), TEXT)
    assert b.quote is None
    q = "completion is expected in 6 months"
    assert make_brief(FakeRouter(_reply(quote=q)), _filing(), TEXT).quote == q


def test_no_summary_and_bad_reply_gives_none():
    f = _filing(summary=None)
    assert make_brief(FakeRouter(_reply("Acme pays ₹9,999 crore.")), f, TEXT) is None
    assert make_brief(FakeRouter({"one_liner": 7}), f, TEXT) is None
    assert make_brief(FakeRouter({"oops": 1}), f, TEXT) is None


def test_only_material_categories_enriched(conn):
    _seed(conn, _filing("D1"), category="dividend")
    _seed(conn, _filing("A1"))
    router = FakeRouter(_reply())
    res = enrich_briefs(conn, FakeNSE({}, {}), router, SINCE, set())
    assert res.done == 1 and len(router.calls) == 1
    assert router.calls[0][0] == "oneliner"
    saved = db.get_enrichments(conn, ["A1", "D1"], "brief")
    assert set(saved) == {"A1"} and saved["A1"]["brief"]["by"] == "llm"


def test_noise_filing_ignored(conn):
    _seed(conn, _filing("A1"), noise=True)
    router = FakeRouter(_reply())
    enrich_briefs(conn, FakeNSE({}, {}), router, SINCE, set())
    assert router.calls == []


def test_llm_error_not_saved_and_no_fallback(conn):
    _seed(conn, _filing("A1"))
    res = enrich_briefs(conn, FakeNSE({}, {}), FakeRouter(LLMError("429")), SINCE, set())
    assert "A1" in res.failed and res.done == 0
    assert db.get_enrichments(conn, ["A1"], "brief") == {}


def test_crash_recorded_and_continues(conn):
    _seed(conn, _filing("A1"))
    _seed(conn, _filing("A2", at=datetime(2026, 11, 5, 11, 0, tzinfo=IST)))

    state = {"n": 0}

    def reply(task, system, user):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("boom")
        return _reply()

    res = enrich_briefs(conn, FakeNSE({}, {}), FakeRouter(reply), SINCE, set())
    assert "A1" in res.failed and res.done == 1


def test_invalid_one_liner_saves_fallback(conn):
    _seed(conn, _filing("A1"))
    res = enrich_briefs(conn, FakeNSE({}, {}), FakeRouter(_reply("₹9,999 crore")), SINCE, set())
    assert res.done == 1
    assert db.get_enrichments(conn, ["A1"], "brief")["A1"]["brief"]["by"] == "nse_summary"


def test_bad_reply_without_summary_saves_null(conn):
    _seed(conn, _filing("A1", summary=None))
    res = enrich_briefs(conn, FakeNSE({}, {}), FakeRouter({"one_liner": 3}), SINCE, set())
    assert res.empty == 1
    assert db.get_enrichments(conn, ["A1"], "brief")["A1"]["brief"] is None


def test_no_text_no_summary_saves_null_empty(conn):
    f = _filing("A1", summary=None, pdf_url=None)
    _seed(conn, f)
    router = FakeRouter(_reply())
    res = enrich_briefs(conn, FakeNSE({}, {}), router, SINCE, set())
    assert res.empty == 1 and router.calls == []
    saved = db.get_enrichments(conn, ["A1"], "brief")["A1"]
    assert saved == {"brief": None, "reason": "no text"}


def test_digest_attaches_headline_brief(conn):
    _seed(conn, _filing("A1"))
    _seed(conn, _filing("A2", at=datetime(2026, 11, 5, 11, 0, tzinfo=IST)))
    row = lambda one, seq: {
        "brief": {"one_liner": one, "facts": [], "quote": None, "by": "llm", "source_seq_id": seq}
    }
    db.save_enrichment(conn, "A1", "brief", row("First.", "A1"), "m")
    db.save_enrichment(conn, "A2", "brief", row("Second.", "A2"), "m")
    d = build_digest(
        conn,
        ["ACME"],
        datetime(2026, 11, 5, 0, 0, tzinfo=IST),
        datetime(2026, 11, 5, 23, 59, tzinfo=IST),
        "everything",
        {"mna"},
    )
    st = next(s for s in d["stories"] if s.category == "mna")
    assert st.brief.one_liner == {"A1": "First.", "A2": "Second."}[st.headline.filing.seq_id]


def test_digest_skips_corrupt_row(conn):
    _seed(conn, _filing("A1"))
    db.save_enrichment(conn, "A1", "brief", {"brief": {"one_liner": 5}}, "m")
    d = build_digest(
        conn,
        ["ACME"],
        datetime(2026, 11, 5, 0, 0, tzinfo=IST),
        datetime(2026, 11, 5, 23, 59, tzinfo=IST),
        "everything",
        {"mna"},
    )
    assert next(s for s in d["stories"] if s.category == "mna").brief is None


def test_tiny_or_partial_nondigit_facts_dropped():
    text = "Rating reaffirmed at CRISIL AA+ with a stable outlook in the filing ltd."
    facts = [
        {"label": "x", "value": "a"},
        {"label": "x", "value": "in"},
        {"label": "x", "value": "ab"},
        {"label": "x", "value": "ratin"},
        {"label": "Rating", "value": "CRISIL AA+"},
    ]
    b = make_brief(FakeRouter(_reply("Rating reaffirmed.", facts)), _filing(), text)
    assert [f.value for f in b.facts] == ["CRISIL AA+"]


def test_short_quote_dropped_long_quote_kept():
    assert make_brief(FakeRouter(_reply(quote="the")), _filing(), TEXT).quote is None
    q = "Completion is expected in 6 months"
    assert make_brief(FakeRouter(_reply(quote=q)), _filing(), TEXT).quote == q
