import pytest

from finn.enrich.grounding import grounded_sentences, name_in_text, normalize, numbers_grounded
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
    assert out is not None
    assert out.startswith("Mr. Jayant Balan is a Mechanical Engineer")
    assert "Nobel" not in out


def test_grounded_sentences_none_when_nothing_kept(voltas):
    assert grounded_sentences("He won a Nobel Prize.", voltas, 90) is None
    assert grounded_sentences("", voltas, 90) is None


def test_grounded_sentences_truncates_on_sentence_boundary():
    text = "One two three. Four five six seven. Eight nine."
    assert grounded_sentences(text, text, 8) == "One two three. Four five six seven."
    assert grounded_sentences(text, text, 5) == "One two three."


def test_grounded_sentences_first_too_long_is_cut():
    text = "One two three four five six."
    assert grounded_sentences(text, text, 3) == "One two three…"


def test_numbers_grounded():
    assert numbers_grounded("₹5,000 crore deal", "deal worth Rs 5000 crore")
    assert not numbers_grounded("₹6,000 crore deal", "deal worth Rs 5000 crore")
    assert numbers_grounded("no numbers here", "anything")
    assert not numbers_grounded("since 2019", "since 2018")
    assert numbers_grounded("since 2019", "since 2019")
