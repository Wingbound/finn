"""Deterministic first-pass classifier for NSE announcements.

Returns None when the filing is ambiguous; those go to the LLM classifier.
"""

from __future__ import annotations

import re

from finn.models import Category, Classification, Filing

SUMMARY_CHARS = 400


def _norm(desc: str) -> str:
    return re.sub(r"\s+", " ", desc).strip().casefold()


NOISE_DESCS: frozenset[str] = frozenset(
    {
        "Copy of Newspaper Publication",
        "Loss of Share Certificates",
        "Loss of share certificate",
        "Issue of Duplicate Share Certificate",
        "Certificate under SEBI (Depositories and Participants) Regulations, 2018",
        "Trading Window",
        "Structural Digital Database",
        "Registrar & Share Transfer Agent Update",
        "Address Change",
        ("Quarterly Compliance Report on Corporate governance - within 21 days from the end "
        "of the quarter"),
        "Integrated Filing- Governance",
    }
)

_MGMT: tuple[Category, None] = ("management_change", None)
_CREDIT: tuple[Category, None] = ("credit_rating", None)
_LIT: tuple[Category, None] = ("litigation", None)
_RAISE: tuple[Category, None] = ("fund_raise", None)
_CAPEX: tuple[Category, None] = ("capex", None)
_DIV: tuple[Category, None] = ("dividend", None)
_SPLIT: tuple[Category, None] = ("bonus_split", None)

DESC_MAP: dict[str, tuple[Category, str | None]] = {
    "Acquisition": ("mna", "acquisition"),
    "Amalgamation/Merger": ("mna", "merger"),
    "Scheme of Arrangement": ("mna", "scheme"),
    "Demerger": ("mna", "demerger"),
    "Sale or disposal": ("mna", "divestment"),
    "Diversification/Disinvestment": ("mna", "divestment"),
    "Open Offer": ("mna", "open_offer"),
    "Public Announcement-Open Offer": ("mna", "open_offer"),
    **{
        d: _MGMT
        for d in (
            "Appointment",
            "Change in Management",
            "Change in Director(s)",
            "Resignation of Director/KMP/SMP",
            "Resignation",
            "Cessation",
            "Retirement",
            "Demise",
            "Change in Company Secretary/Compliance Officer",
        )
    },
    **{
        d: _CREDIT
        for d in (
            "Credit Rating",
            "Credit Rating- New",
            "Credit Rating- Revision",
            "Credit Rating- Others",
        )
    },
    **{
        d: _LIT
        for d in (
            "Action(s) taken or orders passed",
            "Action(s) initiated or orders passed",
            "Pendency of Litigation(s)/dispute(s) or the outcome impacting the Company",
            "Corporate Insolvency Resolution Process",
            "Fraud/Default/Arrest",
            "Initiation of Forensic Audit",
            "Final  forensic  audit  report",
            "Defaults on Payment of Interest/Principal",
        )
    },
    **{
        d: _RAISE
        for d in (
            "Qualified Institutional Placement",
            "Rights Issue",
            "Preferential issue",
            "Issue of Securities",
            "Buyback",
            "Public Announcement - Buyback of Shares",
            "Post Buyback Public Announcement",
            "Closure of Buy Back",
        )
    },
    "Allotment of Securities": ("fund_raise", "allotment"),
    "ESOP/ESOS/ESPS": ("unclassified", "esop"),
    **{
        d: _CAPEX
        for d in (
            "Capacity addition",
            "Commencement of commercial production/operations",
            "Postponement of commercial production/operations",
        )
    },
    "Bagging/Receiving of orders/contracts": ("press_release", "order_win"),
    "Awarding of order(s)/contract(s)": ("press_release", "order_win"),
    "Product launch": ("press_release", "product"),
    "Arrangements for strategic, technical, manufacturing, or marketing tie up": (
        "press_release",
        "partnership",
    ),
    "Memorandum of Understanding/Agreements": ("press_release", "partnership"),
    "Agreements": ("press_release", "partnership"),
    **{
        d: _DIV
        for d in ("Dividend", "Record Date", "Date of payment of dividend", "Revised Record date")
    },
    "Bonus": _SPLIT,
    "Stock split": _SPLIT,
    "Investor Presentation": ("results", "presentation"),
    "Integrated Filing- Financial": ("results", "filing"),
    "Clarification - Financial Results": ("results", "filing"),
    "Reply to Clarification- Financial results": ("results", "filing"),
    "Reasons for Delayed/Non-submission of Financial Results": ("results", "delay"),
    "Disclosure under SEBI Takeover Regulations": ("insider_trading", "sast"),
    "Trading Plan under PIT": ("insider_trading", "plan"),
    "Spurt in Volume": ("press_release", "clarification"),
    "Price movement": ("press_release", "clarification"),
    "News Verification": ("press_release", "clarification"),
    "Rumour Verification - Regulation 30(11)": ("press_release", "clarification"),
    "Change in Auditors": ("unclassified", "auditor"),
    # A red flag, so deliberately not routine.
    "Resignation of Statutory Auditor": ("litigation", "auditor_resignation"),
    "Monitoring Agency Report": ("unclassified", "compliance"),
    "Statement of deviation(s) or variation(s) under Reg. 32": ("unclassified", "compliance"),
    "Utilisation of Funds": ("unclassified", "compliance"),
    "Disruption of Operations": ("litigation", "disruption"),
    "Strikes/Lockouts/Disturbances": ("litigation", "disruption"),
    "Closure of operations": ("litigation", "disruption"),
    "Suspension of Trading": ("litigation", "listing"),
    "Delisting": ("litigation", "listing"),
}

AMBIGUOUS_DESCS: frozenset[str] = frozenset(
    {
        "Outcome of Board Meeting",
        "Analysts/Institutional Investor Meet/Con. Call Updates",
        "General Updates",
        "Updates",
        "Press Release",
        "Press Release (Revised)",
        "Shareholders meeting",
        "Others",
        "Disclosure of material issue",
        "Committee Meeting Updates",
        "Monthly Business Updates",
    }
)

_NOISE_KEYS = {_norm(d) for d in NOISE_DESCS}
_MAP_KEYS = {_norm(k): v for k, v in DESC_MAP.items()}
_AMBIGUOUS_KEYS = {_norm(d) for d in AMBIGUOUS_DESCS}

_INVESTOR_MEET_DESC = _norm("Analysts/Institutional Investor Meet/Con. Call Updates")

_ESOP = re.compile(r"ESOP|ESOS|ESPS|employee stock", re.IGNORECASE)

_ROLE_CXO = re.compile(
    r"chief executive|\bceo\b|chief financial|\bcfo\b|managing director|\bmd\b"
    r"|whole[- ]?time director|chairman|chairperson",
    re.IGNORECASE,
)
_ROLE_INDEP = re.compile(r"independent director|non-?\s?executive", re.IGNORECASE)
_ROLE_CS = re.compile(r"company secretary|compliance officer", re.IGNORECASE)

_RATING_SUBTYPES = (
    (re.compile(r"upgrad", re.IGNORECASE), "upgrade"),
    (re.compile(r"downgrad", re.IGNORECASE), "downgrade"),
    (re.compile(r"reaffirm", re.IGNORECASE), "reaffirm"),
    (re.compile(r"-\s?New\b", re.IGNORECASE), "new"),
)

# First match wins. Order matters: the intimation rule precedes the results rule
# because intimations also say "to consider and approve the unaudited financial results".
_KEYWORD_RULES: tuple[tuple[re.Pattern[str], Category, str | None], ...] = tuple(
    (re.compile(pat, re.IGNORECASE), cat, sub)
    for pat, cat, sub in (
        (r"\btranscripts?\b", "earnings_call", "transcript"),
        (r"\baudio\b|\brecording", "earnings_call", "audio"),
        (r"\bcon(ference)?[ .-]?calls?\b|\bearnings calls?\b", "earnings_call", "notice"),
        (r"scheduled .*(to consider|inter alia).*results", "results", "intimation"),
        ((r"(financial )?results.*(approv|unaudited|audited|outcome)"
         r"|(approv|unaudited|audited|outcome).*(financial )?results"),
         "results", "results"),
        (r"submitted to the exchange,? the (unaudited |audited )?financial results",
         "results", "results"),
        (r"press release.*results", "results", "press_release"),
        (r"\bdividend", "dividend", None),
        ((r"\bacqui|\bmerger|\bamalgamat|\bdemerg|\bjoint venture|\bstake\b|\btakeover"
         r"|\bscheme of arrangement"), "mna", None),
        ((r"\bappoint(?!ment of (statutory|secretarial|internal|cost) auditors?)|\bresign|\bcessation\b|\bre-?designat|\bchief executive"
         r"|\bchief financial|\bmanaging director"), "management_change", None),
        ((r"\bqip\b|\binitial public offer|\brights issue|\bpreferential|\bbuy-?back|\bfund ?rais"
         r"|\bnon-convertible|\bncds?\b|\bcommercial paper"), "fund_raise", None),
        (r"\bpostal ballot", "postal_ballot", None),
        (r"\bcourt[- ]convened\b", "agm_egm", "court_convened"),
        (r"\bannual general meeting|\bagm\b|\bextra-?ordinary general meeting|\begm\b",
         "agm_egm", None),
        (r"\b(investor|analyst)s?\b.*\bmeet|\b(investor|analyst)s?\b.*\bconference",
         "investor_meetings", None),
        ((r"\b(secur\w*|bag\w*|receiv\w*|win|wins|won|awarded|award)\b.{0,40}\b(orders?|contracts?)\b"
         r"|\b(orders?|contracts?)\b.{0,25}\b(worth|valued|aggregating)\b"),
         "press_release", "order_win"),
        (r"\blaunch(es|ed)?\b", "press_release", "product"),
        ((r"\bmou\b|memorandum of understanding|strategic partner|\bpartnership\b"
         r"|\bpartners? (to|with)\b"
         r"|\b(signs?|signed|enters?|entered into|executes?|executed)\b"
         r"(?!.{0,30}\b(settlement|lease|loan|credit|share swap)\b).{0,30}\bagreements?\b"),
         "press_release", "partnership"),
        ((r"\bcapacity (addition|expansion)|\bcapex\b|\bcapital expenditure|\bnew (plant|facility)"
         r"|\bexpansion\b"), "capex", None),
        (r"\bmonthly\b|\bbusiness updates?\b|\bsales\b", "press_release", "business_update"),
    )
)


def management_subtype(text: str) -> str:
    """Scoring subtype of a management change, from its desc/subject/summary text."""
    if _ROLE_CXO.search(text):
        return "cxo"
    if _ROLE_INDEP.search(text):
        return "independent"
    if _ROLE_CS.search(text):
        return "cs"
    return "director"


def credit_subtype(text: str) -> str | None:
    """Scoring subtype of a credit-rating action, from its desc/subject/summary text."""
    for pattern, subtype in _RATING_SUBTYPES:
        if pattern.search(text):
            return subtype
    return None


def classify_rules(f: Filing) -> Classification | None:
    desc = _norm(f.nse_desc)
    text = f"{f.subject} {(f.nse_summary or '')[:SUMMARY_CHARS]}"

    if desc in _NOISE_KEYS:
        return Classification(
            category="unclassified", noise=True, by="rules", confidence=0.95
        )

    if desc in _MAP_KEYS:
        category, subtype = _MAP_KEYS[desc]
        if desc == _norm("Allotment of Securities") and _ESOP.search(text):
            category, subtype = "unclassified", "esop"
        elif category == "management_change":
            subtype = management_subtype(f"{f.nse_desc} {text}")
        elif category == "credit_rating":
            subtype = credit_subtype(f"{f.nse_desc} {text}")
        return Classification(category=category, subtype=subtype, by="rules", confidence=0.95)

    if desc in _AMBIGUOUS_KEYS:
        for pattern, category, subtype in _KEYWORD_RULES:
            if pattern.search(text):
                if category == "management_change":
                    subtype = management_subtype(text)
                return Classification(
                    category=category, subtype=subtype, by="rules", confidence=0.8
                )
        if desc == _INVESTOR_MEET_DESC:
            # NSE's own tag; earnings-call/transcript/results cases were caught above.
            return Classification(category="investor_meetings", by="rules", confidence=0.8)
    return None
