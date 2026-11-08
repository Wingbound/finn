import pytest

from finn.classify.materiality import BASE_SCORES, score_filing
from finn.models import CATEGORIES, Classification, Filing


def _f(seq="1") -> Filing:
    return Filing(
        seq_id=seq,
        symbol="X",
        company="X Ltd",
        nse_desc="d",
        subject="s",
        filed_at="2026-11-01T10:00:00+05:30",
    )


def _c(cat, subtype=None, noise=False) -> Classification:
    return Classification(category=cat, subtype=subtype, noise=noise, by="rules", confidence=1.0)


EXPECTED = {
    "results": 90,
    "mna": 85,
    "management_change": 80,
    "pledging": 75,
    "litigation": 75,
    "credit_rating": 70,
    "fund_raise": 70,
    "capex": 60,
    "insider_trading": 50,
    "bonus_split": 40,
    "press_release": 35,
    "earnings_call": 30,
    "dividend": 30,
    "agm_egm": 15,
    "postal_ballot": 15,
    "investor_meetings": 10,
    "unclassified": 5,
}


def test_expected_covers_all_categories():
    assert set(EXPECTED) == set(CATEGORIES) and len(EXPECTED) == 17
    assert BASE_SCORES == EXPECTED


@pytest.mark.parametrize("cat,base", sorted(EXPECTED.items()))
def test_base_scores_match_spec(cat, base):
    assert score_filing(_f(), _c(cat), set()).score == base


def test_cfo_change_is_critical():
    s = score_filing(_f(), _c("management_change", "cxo"), set())
    assert s.score == 88 and s.tier == "critical"
    assert "CFO/CEO/MD change ×1.1" in s.reasons


def test_rating_reaffirm_is_routine():
    s = score_filing(_f(), _c("credit_rating", "reaffirm"), set())
    assert s.score == 24 and s.tier == "routine"


def test_transcript_is_important():
    s = score_filing(_f(), _c("earnings_call", "transcript"), set())
    assert s.score == 45 and s.tier == "important"


def test_unknown_subtype_has_no_modifier():
    assert score_filing(_f(), _c("results", "weird"), set()).score == 90


def test_noise_is_zero():
    s = score_filing(_f(), _c("results", "results", noise=True), {"results"})
    assert s.score == 0 and s.tier == "noise" and s.reasons == ["routine paperwork"]


def test_subscription_boost_and_cap():
    s = score_filing(_f(), _c("capex"), {"capex"})
    assert s.score == 70 and "you follow capex +10" in s.reasons
    s = score_filing(_f(), _c("results"), {"results"})
    assert s.score == 100 and s.tier == "critical"
