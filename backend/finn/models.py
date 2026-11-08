"""Shared data models."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

IST = timezone(timedelta(hours=5, minutes=30), "IST")

Category = Literal[
    "results",
    "mna",
    "fund_raise",
    "management_change",
    "litigation",
    "insider_trading",
    "earnings_call",
    "investor_meetings",
    "credit_rating",
    "dividend",
    "bonus_split",
    "capex",
    "press_release",
    "postal_ballot",
    "agm_egm",
    "pledging",
    "unclassified",
]

CATEGORIES: tuple[str, ...] = get_args(Category)


class Filing(BaseModel):
    seq_id: str
    symbol: str
    company: str
    nse_desc: str
    subject: str
    nse_summary: str | None = None
    pdf_url: str | None = None
    filed_at: datetime
    has_xbrl: bool = False

    @field_validator("filed_at")
    @classmethod
    def _aware_ist(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("filed_at must be timezone-aware")
        return v.astimezone(IST)


class Classification(BaseModel):
    category: Category
    subtype: str | None = None
    noise: bool = False
    by: Literal["rules", "llm", "default"]
    confidence: float


class PriceBar(BaseModel):
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


Tier = Literal["critical", "important", "routine", "noise"]


class ScoredFiling(BaseModel):
    filing: Filing
    cls: Classification
    score: int
    tier: Tier
    reasons: list[str]


class Story(BaseModel):
    id: str
    symbol: str
    company: str
    category: Category
    subtype: str | None = None
    score: int
    tier: Tier
    headline: ScoredFiling
    members: list[ScoredFiling]
    latest_at: datetime


class SymbolOverride(BaseModel):
    volume_multiple: float | None = None
    price_move_pct: float | None = None
    muted: bool = False


class Rules(BaseModel):
    volume_multiple: float = 2.0
    price_move_pct: float = 5.0
    lookback: int = 20
    categories: set[Category] = Field(
        default_factory=lambda: {
            "results",
            "mna",
            "management_change",
            "credit_rating",
            "litigation",
            "pledging",
            "fund_raise",
        }
    )
    overrides: dict[str, SymbolOverride] = Field(default_factory=dict)


class Alert(BaseModel):
    kind: Literal["volume", "price", "filing"]
    symbol: str
    date: date
    value: float
    threshold: float
    message: str
    story_id: str | None = None
