import pytest

from finn.llm.providers import LLMError
from finn.models import Citation, Source
from finn.research.guidance import _forward_looking, extract_promises
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


# ---- I4: conditionals and past facts ----
PAGE = (
    "If demand recovers, we will grow revenue by 15% in FY27. "
    "Assuming the order inflow sustains, we expect EBITDA margin of 12% next year. "
    "Unless the macro deteriorates further, we will deliver revenue growth of 15% in FY27. "
    "Our plant utilization was 80% in the quarter. "
    "As expected, revenue grew 12% this quarter. "
    "We are willing to consider acquisitions in adjacent areas. "
    "Provided approvals come through, the new plant will start in Q3 FY27. "
    "Subject to board approval, we will pay a special dividend this year. "
    "We expect revenue to grow 15% in FY27."
)


def synthetic() -> Source:
    return Source(id="S1", kind="transcript", title="Q2 FY27 call", quarter="Q2 FY27", url="u", pages=[PAGE])  # fmt: skip


@pytest.mark.parametrize(
    "quote",
    [
        "If demand recovers, we will grow revenue by 15% in FY27.",
        "we will grow revenue by 15% in FY27",  # fragment after "If demand recovers,"
        "Assuming the order inflow sustains, we expect EBITDA margin of 12% next year.",
        "we expect EBITDA margin of 12% next year",
        "we will deliver revenue growth of 15% in FY27",  # cut after "Unless ... further,"
        "Our plant utilization was 80% in the quarter.",
        "As expected, revenue grew 12% this quarter.",
        "We are willing to consider acquisitions in adjacent areas.",
        "the new plant will start in Q3 FY27",
        "we will pay a special dividend this year",
    ],
)
def test_conditional_and_past_statements_dropped(quote):
    guard: dict = {}
    out = extract_promises(FakeRouter({"promises": [item(quote)]}), synthetic(), guard)
    assert out == [] and guard == {"promises_proposed": 1, "promises_kept": 0}


def test_plain_forward_statement_kept():
    out = extract_promises(FakeRouter({"promises": [item("We expect revenue to grow 15% in FY27.")]}), synthetic())  # fmt: skip
    assert [p.citation.quote for p in out] == ["We expect revenue to grow 15% in FY27."]


@pytest.mark.parametrize(
    "quote",
    [
        "We expect growth", "Management expects growth", "We are expecting growth",
        "Revenue will grow", "We shall invest", "It would help", "We plan to invest",
        "It plans to invest", "We are planning a plant", "We aim to lead", "It aims to lead",
        "We are aiming higher", "Our target is 15%", "We are targeting 15%", "Two targets set",
        "We guide for 15%", "Our guidance is 15%", "We are guiding 15%", "We intend to invest",
        "It intends to invest", "We are intending to invest", "We anticipate growth",
        "It anticipates growth", "We are anticipating growth", "We aspire to lead",
        "It aspires to lead", "Our aspiration is to lead", "We commit capital",
        "We are committed to growth", "It commits capital", "The outlook is good",
        "Going forward, margins rise", "We are on track", "The upcoming launch",
        "Margins should rise", "Growth is likely", "We are confident", "We look to grow",
        "We are looking to grow", "We look forward to it", "Breakeven by FY27",
        "Breakeven by FY 27", "The next phase",
    ],
)  # fmt: skip
def test_forward_cues_whole_words(quote):
    assert _forward_looking(quote)


@pytest.mark.parametrize(
    "quote",
    [
        "As expected, revenue grew 12%", "We had planned this", "We targeted 15% and got it",
        "We aimed high", "Our new plant runs well", "Customers are willing to pay",
        "We guided 15% last year", "The endeavour paid off", "Our commitment is long",
    ],
)  # fmt: skip
def test_past_forms_and_prefixes_are_not_cues(quote):
    assert not _forward_looking(quote)


def test_system_prompt_excludes_conditionals():
    from finn.research.guidance import SYSTEM

    assert (
        "Exclude conditional or hypothetical statements (if, unless, assuming, provided, subject to)."
        in SYSTEM
    )


@pytest.mark.parametrize(
    "quote",
    [
        "Capacity is expected to come on stream by end of this calendar year.",
        "The plant is planned to be commissioned in Q3.",
        "The new facility is scheduled to start by March 2027.",
        "Revenue is projected to grow 15% in FY27.",
        "The order book remains poised to grow.",
    ],
)
def test_passive_future_forms_are_cues(quote):
    assert _forward_looking(quote)


@pytest.mark.parametrize(
    "quote",
    [
        "As expected, revenue grew 12%.",
        "Demand was expected to recover but did not.",
        "Our plant utilization was 80%.",
        "Segment profitability stood at ₹ 272 million, translating to a margin of 6.7%.",
    ],
)
def test_passive_past_forms_are_not_cues(quote):
    assert not _forward_looking(quote)


@pytest.mark.parametrize(
    "quote",
    [
        "The plant was planned to be commissioned in FY24 but slipped.",
        "The unit had been scheduled to be completed last year.",
        "The line was expected to be operational in 2023.",
        "The plant was not expected to be commissioned.",
    ],
)
def test_past_passives_with_participles_are_not_cues(quote):
    assert not _forward_looking(quote)
