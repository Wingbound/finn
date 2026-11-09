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


class PersonChange(BaseModel):
    name: str
    role: str | None = None
    change: Literal["appointed", "resigned", "retired", "ceased", "redesignated", "other"]
    effective: str | None = None  # as written in the filing
    profile: str | None = None  # grounded sentences only, at most 90 words
    incoming: bool  # change in {"appointed", "redesignated"}
    source_seq_id: str


class Fact(BaseModel):
    label: str
    value: str


class Brief(BaseModel):
    one_liner: str
    facts: list[Fact] = []
    quote: str | None = None
    by: Literal["llm", "nse_summary"]
    source_seq_id: str


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
    people: list[PersonChange] = Field(default_factory=list)
    brief: Brief | None = None


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


class Flag(BaseModel):
    level: Literal["good", "watch", "concern"]
    text: str


class Trajectory(BaseModel):
    years: list[str]
    revenue: list[float | None]
    operating_profit: list[float | None]
    margin_pct: list[float | None]
    pat: list[float | None]
    revenue_cagr_pct: float | None
    pat_cagr_pct: float | None
    margin_change_bps: int | None
    read: Literal["growing", "compressing", "mixed", "insufficient data"]
    lender: bool


class BalanceSheetHealth(BaseModel):
    as_of: str
    debt_to_equity: float | None
    cfo_to_pat_3y: float | None
    fcf_3y_cr: float | None
    working_capital_days: float | None
    wc_days_change_3y: float | None
    roce_pct: float | None
    flags: list[Flag]


class Source(BaseModel):
    id: str
    kind: Literal["transcript", "annual_report"]
    title: str
    quarter: str | None
    url: str
    pages: list[str]


class Citation(BaseModel):
    source_id: str
    page: int  # 1-based
    quote: str


class Promise(BaseModel):
    id: str  # f"{source_id}-{n}"
    citation: Citation
    topic: str
    kind: Literal["quantitative", "qualitative"]
    metric: (
        Literal[
            "revenue_growth",
            "ebitda_margin",
            "pat_growth",
            "capex",
            "order_book",
            "volume_growth",
            "other",
        ]
        | None
    ) = None
    target_low: float | None = None
    target_high: float | None = None
    unit: Literal["%", "cr", "x", "usd_mn", "usd_bn"] | None = None
    horizon: str | None = None  # as said: "Q3 FY27", "FY27", "next year"
    made_in: str  # the source's quarter


Status = Literal["kept", "partly", "missed", "pending", "dropped"]


class Actual(BaseModel):
    value: float
    unit: str
    period: str  # "Q2 FY27" | "FY26"
    basis: str  # e.g. "YoY revenue growth from screener quarterly table"


class LedgerRow(BaseModel):
    promise: Promise
    status: Status
    method: Literal["computed", "judged"]
    actual: Actual | None = None
    evidence: Citation | None = None  # from a LATER source than the promise
    rationale: str  # one plain sentence


class Ledger(BaseModel):
    rows: list[LedgerRow]
    counts: dict[str, int]  # per status
    credibility_pct: float | None  # (kept + 0.5*partly) / (kept + partly + missed) * 100
    note: str | None = None


class Point(BaseModel):
    text: str  # at most 30 words
    citation: Citation


class Snapshot(BaseModel):
    summary: list[Point]  # 2-4 cited sentences on what the company does
