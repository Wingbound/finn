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
    results: ResultsCard | None = None


class SymbolOverride(BaseModel):
    volume_multiple: float | None = Field(None, gt=0, le=100)
    price_move_pct: float | None = Field(None, gt=0, le=100)
    muted: bool = False


class Rules(BaseModel):
    volume_multiple: float = Field(2.0, gt=0, le=100)
    price_move_pct: float = Field(5.0, gt=0, le=100)
    lookback: int = Field(20, ge=5, le=250)
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
    seq_id: str | None = None  # filing alerts: the headline filing, a stable link target


class MetricRow(BaseModel):
    key: str
    label: str
    value: float | None  # INR crore, 2 dp
    qoq_pct: float | None = None
    yoy_pct: float | None = None
    computed: bool = False  # derived by FINN, not a reported line


class MarginRow(BaseModel):
    key: str
    label: str
    value_pct: float | None
    qoq_bps: int | None = None
    yoy_bps: int | None = None


class ResultsCard(BaseModel):
    symbol: str
    period_end: date
    period_label: str
    basis: Literal["consolidated", "standalone"]
    format: Literal["indas", "nbfc", "bank"]
    audited: bool | None
    compared_qoq: date | None
    compared_yoy: date | None
    metrics: list[MetricRow]
    margins: list[MarginRow]
    notes: list[str]
    sources: list[str]
