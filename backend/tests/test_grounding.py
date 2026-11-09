import pytest

from finn.enrich.grounding import (
    grounded_sentences,
    name_in_text,
    normalize,
    numbers_grounded,
    split_sentences,
)
from tests.fakes import FIXTURES


@pytest.fixture(scope="module")
def voltas() -> str:
    return (FIXTURES / "pdf" / "106850979.txt").read_text()


REAL = (
    "Mr. Jayant Balan is a Mechanical Engineer and PGDM from SP Jain Institute of "
    "Management & Research."
)


def test_normalize_folds_ligatures_quotes_whitespace():
    assert normalize("Ofﬁce  D’Souza\n") == "office d'souza"


def test_name_in_text(voltas):
    assert name_in_text("Mr. Jayant Balan", voltas)
    assert name_in_text("Sunil Alaric D’Souza", voltas)
    assert name_in_text("Sunil Alaric D'Souza", voltas)
    assert not name_in_text("John Doe", voltas)
    assert not name_in_text("Mr.", voltas)


def test_grounded_sentences_drops_invented(voltas):
    out = grounded_sentences(REAL + " He also won a Nobel Prize.", voltas, 90)
    assert out == REAL


def test_grounded_sentences_none_when_nothing_kept(voltas):
    assert grounded_sentences("He won a Nobel Prize.", voltas, 90) is None
    assert grounded_sentences("", voltas, 90) is None


def test_grounded_sentences_truncates_on_sentence_boundary():
    text = "One two three four. Five six seven eight nine. Ten eleven twelve thirteen."
    assert grounded_sentences(text, text, 9) == "One two three four. Five six seven eight nine."
    assert grounded_sentences(text, text, 5) == "One two three four."


def test_grounded_sentences_first_too_long_is_cut():
    text = "One two three four five six."
    assert grounded_sentences(text, text, 5) == "One two three four five…"


def test_numbers_grounded():
    assert numbers_grounded("₹5,000 crore deal", "deal worth Rs 5000 crore")
    assert not numbers_grounded("₹6,000 crore deal", "deal worth Rs 5000 crore")
    assert numbers_grounded("no numbers here", "anything")
    assert not numbers_grounded("since 2019", "since 2018")
    assert numbers_grounded("since 2019", "since 2019")


def test_name_in_text_word_boundary_and_min_tokens(voltas):
    assert not name_in_text("Ann", "see Annexure A.")
    assert not name_in_text("Balan", voltas)
    assert not name_in_text("Mr. Balan", voltas)
    assert name_in_text("Jayant Balan", voltas)
    assert not name_in_text("Jayant Bal", voltas)


def test_splitter_keeps_honorifics_and_initials_together():
    s = split_sentences(
        "Mr. Jayant Balan is an engineer. Mr. Noel N. Tata will retire. Dr. Rao agreed."
    )
    assert s == [
        "Mr. Jayant Balan is an engineer.",
        "Mr. Noel N. Tata will retire.",
        "Dr. Rao agreed.",
    ]
    assert split_sentences("C.P. Menon is MD. He leaves.") == ["C.P. Menon is MD.", "He leaves."]


def test_bare_honorific_fragment_never_returned():
    text = "Mr. Jayant Balan is an engineer at the firm."
    assert grounded_sentences("Mr. John Doe won a Nobel Prize.", text, 90) is None
    assert grounded_sentences("Mr.", text, 90) is None


def test_phrase_in_text():
    from finn.enrich.grounding import phrase_in_text

    src = "Rating reaffirmed: CRISIL AA+ with stable outlook."
    assert phrase_in_text("crisil  aa+", src)
    assert not phrase_in_text("ratin", src)
    assert not phrase_in_text("", src)
    assert not phrase_in_text("stable outlook", src, min_words=3)
    assert phrase_in_text("with stable outlook", src, min_words=3)


def test_period_labels_are_not_numbers():
    from finn.enrich.grounding import numbers_grounded

    assert not numbers_grounded("27", "margin target for FY27")
    assert numbers_grounded("27", "27% margin in FY27")
    assert numbers_grounded("Q2 revenue 100", "revenue was 100")
    assert not numbers_grounded("2", "Q2 H1 9M 2Q")
