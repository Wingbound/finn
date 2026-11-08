"""Materiality scoring: category base score x subtype modifier (+ subscription boost)."""

from __future__ import annotations

from finn.models import Category, Classification, Filing, ScoredFiling, Tier

BASE_SCORES: dict[str, int] = {
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

# (category, subtype) -> (multiplier, reason label)
MODIFIERS: dict[tuple[str, str], tuple[float, str]] = {
    ("management_change", "cxo"): (1.1, "CFO/CEO/MD change"),
    ("management_change", "independent"): (0.6, "independent director change"),
    ("management_change", "cs"): (0.6, "company secretary change"),
    ("credit_rating", "downgrade"): (1.15, "rating downgrade"),
    ("credit_rating", "reaffirm"): (0.35, "rating reaffirmed"),
    ("credit_rating", "new"): (0.7, "new rating"),
    ("results", "intimation"): (0.3, "results intimation only"),
    ("results", "delay"): (0.9, "results delay"),
    ("results", "presentation"): (0.9, "investor presentation"),
    ("earnings_call", "transcript"): (1.5, "call transcript"),
    ("earnings_call", "audio"): (0.5, "call audio"),
    ("earnings_call", "notice"): (0.5, "call notice"),
    ("press_release", "order_win"): (1.3, "order win"),
    ("fund_raise", "allotment"): (0.6, "allotment"),
    ("litigation", "auditor_resignation"): (1.1, "auditor resignation"),
}

SUBSCRIPTION_BOOST = 10

_LABELS: dict[str, str] = {"mna": "M&A"}


def _label(category: Category) -> str:
    return _LABELS.get(category, category.replace("_", " "))


def tier_for(score: int) -> Tier:
    if score >= 75:
        return "critical"
    if score >= 45:
        return "important"
    return "routine"


def score_filing(f: Filing, cls: Classification, subscribed: set[Category]) -> ScoredFiling:
    if cls.noise:
        return ScoredFiling(
            filing=f, cls=cls, score=0, tier="noise", reasons=["routine paperwork"]
        )

    base = BASE_SCORES[cls.category]
    reasons = [f"{_label(cls.category)} filing ({base})"]
    score = base
    mod = MODIFIERS.get((cls.category, cls.subtype or ""))
    if mod:
        mult, label = mod
        score = round(base * mult)
        reasons.append(f"{label} ×{mult:g}")
    if cls.category in subscribed:
        score += SUBSCRIPTION_BOOST
        reasons.append(f"you follow {_label(cls.category)} +{SUBSCRIPTION_BOOST}")
    score = min(score, 100)
    return ScoredFiling(filing=f, cls=cls, score=score, tier=tier_for(score), reasons=reasons)
