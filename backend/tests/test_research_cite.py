import json

from finn.models import Citation, Source
from finn.research.cite import locate, sentence_prefix, tagged_text
from tests.fakes import FIXTURES

REAL = (
    "Please note that all participants' lines will be in listen-only mode and there will be "
    "an opportunity for you to ask questions after management's opening remarks."
)


def t1() -> Source:
    d = json.loads((FIXTURES / "research" / "PERSISTENT_transcripts.json").read_text())[0]
    return Source(
        id="PERSISTENT-T1",
        kind="transcript",
        title="Q2 FY27 call",
        quarter="Q2 FY27",
        url=d["url"],
        pages=d["pages"],
    )


def test_locate_corrects_wrong_hint():
    c = locate(REAL, t1(), hint_page=9)
    assert c is not None and c.page == 3 and c.source_id == "PERSISTENT-T1"
    assert c.quote == REAL


def test_locate_whitespace_and_case_insensitive():
    c = locate("  " + REAL.upper().replace(" ", "  ") + " ", t1(), None)
    assert c is not None and c.page == 3


def test_locate_paraphrase_none():
    assert (
        locate("Management said everyone may ask questions once remarks are done.", t1(), 3) is None
    )


def test_locate_short_quote_none():
    assert locate("lines will be in listen-only", t1(), 3) is None


def test_locate_across_page_break():
    s = Source(
        id="x",
        kind="transcript",
        title="t",
        quarter=None,
        url="u",
        pages=["intro words here we expect revenue to grow", "by twenty percent next year overall"],
    )
    c = locate("we expect revenue to grow by twenty percent next year", s, None)
    assert c is not None and c.page == 1


def test_tagged_text_markers_and_truncation():
    s = t1()
    full = tagged_text(s)
    assert full.startswith("[[p1]]") and "[[p3]]" in full
    cut = tagged_text(s, max_chars=len(s.pages[0]) + len(s.pages[1]) + 40)
    assert "[[p2]]" in cut and "[[p3]]" not in cut
    assert len(cut) <= len(s.pages[0]) + len(s.pages[1]) + 40


def _page(text):
    return Source(id="n", kind="transcript", title="t", quarter=None, url="u", pages=[text])


NEG = "We do not expect revenue to grow by 20% this year."


def test_locate_rejects_fragment_after_negation():
    assert locate("expect revenue to grow by 20% this year", _page(NEG), None) is None


def test_locate_keeps_quote_containing_negation():
    assert locate(NEG.rstrip("."), _page(NEG), None) is not None


def test_locate_negation_in_previous_sentence_ok():
    s = _page("We did not win that deal. We expect revenue to grow by 20% this year.")
    assert locate("expect revenue to grow by 20% this year", s, None) is not None


def test_locate_other_occurrence_without_negation_accepted():
    s = Source(
        id="n",
        kind="transcript",
        title="t",
        quarter=None,
        url="u",
        pages=[NEG, "Overall we expect revenue to grow by 20% this year."],
    )
    c = locate("expect revenue to grow by 20% this year", s, None)
    assert c is not None and c.page == 2


def test_sentence_prefix():
    src = Source(id="S", kind="transcript", title="t", quarter="Q2 FY27", url="u", pages=[
        "Results were fine. Unless the macro deteriorates further, we will deliver revenue growth of 15% in FY27.",
        "We will hire more people in the year ahead. Then",
    ])  # fmt: skip
    c = locate("we will deliver revenue growth of 15% in FY27", src, None)
    assert c is not None and c.page == 1
    assert sentence_prefix(c, src) == "unless the macro deteriorates further, "
    whole = Citation(source_id="S", page=2, quote="We will hire more people in the year ahead.")
    assert sentence_prefix(whole, src) == ""
    assert sentence_prefix(Citation(source_id="S", page=9, quote="x"), src) == ""
