from finn.llm.providers import LLMError
from finn.models import Citation
from finn.research.guidance import extract_promises
from tests.fakes import FakeRouter
from tests.test_research_cite import REAL, t1

TAX = (
    "Over the next two quarters, we expect an incremental amount ranging between USD 25 to 30 "
    "million to be incurred towards the Nagarro transaction."
)


def item(quote, page=1, **kw):
    d = {"quote": quote, "page": page, "topic": "tax", "kind": "qualitative"}
    d.update(kw)
    return d


def run(promises):
    return extract_promises(FakeRouter({"promises": promises}), t1())


def test_real_quote_wrong_page_kept_and_fixed():
    out = run([item(REAL, page=20)])
    assert len(out) == 1
    p = out[0]
    assert p.citation.page == 3 and p.id == "PERSISTENT-T1-1" and p.made_in == "Q2 FY27"


def test_invented_quote_dropped():
    assert run([item("We will triple our revenue by next March without any new hiring.")]) == []


def test_ungrounded_target_becomes_qualitative():
    out = run(
        [
            item(
                REAL,
                kind="quantitative",
                metric="revenue_growth",
                target_low=25,
                target_high=None,
                unit="%",
            )
        ]
    )
    p = out[0]
    assert p.kind == "qualitative" and p.target_low is None and p.unit is None


def test_grounded_target_kept():
    out = run(
        [
            item(
                TAX,
                kind="quantitative",
                metric="other",
                target_low=25,
                unit="%",
                horizon="Q3 FY27",
            )
        ]
    )
    p = out[0]
    assert p.kind == "quantitative" and p.target_low == 25 and p.unit == "%"
    assert p.horizon == "Q3 FY27" and p.citation.page == 9


def test_dedupe_and_sequential_ids():
    out = run([item(REAL), item(REAL.upper()), item(TAX)])
    assert [p.id for p in out] == ["PERSISTENT-T1-1", "PERSISTENT-T1-2"]


def test_unknown_enums_become_none():
    out = run([item(REAL, metric="vibes", unit="lakh")])
    assert out[0].metric is None and out[0].unit is None


def test_non_string_fields_no_crash():
    out = run(
        [
            item(123),
            item(None),
            "junk",
            item(REAL, topic=5),
            item(REAL, page="3", target_low="x"),
            item(TAX, page=None, horizon=7, target_low=True),
        ]
    )
    assert [p.citation.page for p in out] == [3, 9]
    assert out[1].horizon is None and out[1].target_low is None


def test_llm_error_and_bad_shapes():
    assert extract_promises(FakeRouter(LLMError("down")), t1()) == []
    assert extract_promises(FakeRouter({"promises": "x"}), t1()) == []
    assert extract_promises(FakeRouter({"other": []}), t1()) == []


def test_llm_error_and_bad_shapes_are_reported():
    for rep in (LLMError("down"), {"promises": "x"}, {"other": []}, ["not a dict"]):
        notes: list[str] = []
        assert extract_promises(FakeRouter(rep), t1(), notes=notes) == []
        assert notes == ["Guidance from Q2 FY27 call could not be read (model unavailable)"]
    notes = []
    extract_promises(FakeRouter({"promises": []}), t1(), notes=notes)
    assert notes == []  # an empty list is a valid answer


def test_prompt_header_and_task():
    r = FakeRouter({"promises": []})
    extract_promises(r, t1())
    task, _, user = r.calls[0]
    assert task == "extract_transcript" and "Q2 FY27" in user and "[[p1]]" in user


def test_kind_follows_targets():
    q = run([item(TAX, kind="qualitative", target_low=25, unit="%")])[0]
    assert q.kind == "quantitative"
    q = run([item(TAX, kind="quantitative", unit="%")])[0]
    assert q.kind == "qualitative" and q.unit is None
    q = run([item(TAX, kind="quantitative", target_low=99, unit="%")])[0]
    assert q.kind == "qualitative" and q.unit is None and q.target_low is None


def test_system_prompt_forward_looking_only():
    from finn.research.guidance import SYSTEM

    r = FakeRouter({"promises": []})
    extract_promises(r, t1())
    assert "forward-looking" in r.calls[0][1] and r is not None
    assert "Exclude statements of current or past fact" in SYSTEM


def _quote_in_t1(sentence):
    from finn.research.cite import locate

    return locate(sentence, t1(), None)


def test_future_cue_required(monkeypatch):
    import finn.research.guidance as g

    sents = {
        "past": "Segment profitability stood at ₹ 272 million, translating to a margin of 6.7%.",
        "cond": "If Vivo comes in, then it's a very major trigger.",
        "expect": "We expect margins to improve over the coming quarters.",
        "track": "we remain on track to reach the stated margin goal.",
    }
    monkeypatch.setattr(g, "locate", lambda q, s, h: Citation(source_id=s.id, page=1, quote=q))
    out = g.extract_promises(FakeRouter({"promises": [item(q) for q in sents.values()]}), t1())
    assert [p.citation.quote for p in out] == [sents["expect"], sents["track"]]
