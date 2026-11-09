"""Parse NSE integrated-filing XBRL (Ind-AS, NBFC, bank) into one quarter's facts."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from finn.models import IST

log = logging.getLogger(__name__)

XbrlFormat = Literal["indas", "nbfc", "bank"]
Basis = Literal["consolidated", "standalone"]

_FINANCIALS_TYPE = "Integrated Filing- Financials"
_XBRLI = "{http://www.xbrl.org/2003/instance}"


class XbrlError(Exception):
    """The XBRL document is malformed or lacks a usable quarter."""


class FinancialsFiling(BaseModel):
    symbol: str
    period_end: date
    basis: Basis
    audited: bool | None
    filed_at: datetime  # first broadcast of this period+basis, not the revision time
    xbrl_url: str
    format: XbrlFormat | None
    revised: bool = False  # the document is a revision of the first broadcast


class QuarterFinancials(BaseModel):
    symbol: str
    period_start: date
    period_end: date
    basis: Basis
    format: XbrlFormat
    audited: bool | None
    facts: dict[str, float]


def detect_format(url: str) -> XbrlFormat | None:
    u = url.upper()
    if "BANKING" in u:
        return "bank"
    if "NBFC" in u:
        return "nbfc"
    if "INDAS" in u:
        return "indas"
    return None


def _audited(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    if v == "audited":
        return True
    if v in ("un-audited", "unaudited"):
        return False
    return None


def _basis(value: str | None) -> Basis | None:
    v = (value or "").strip().lower()
    return v if v in ("consolidated", "standalone") else None  # type: ignore[return-value]


def _timestamp(value: object) -> datetime | None:
    """NSE list timestamps: "07-Nov-2026 17:33:17" or "31-OCT-2025 23:59:50" (%b ignores case)."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    except ValueError:
        return None


def parse_filing_list(rows: list[dict]) -> list[FinancialsFiling]:
    """One filing per (period_end, basis): the latest row (revisions included) supplies the
    document; filed_at is the earliest broadcast, so a revision never moves the card's date.

    Revised rows carry `broadcast_Date: null` and a `revised_Date`. A row is dropped only
    when it has neither date (or neither parses).
    """
    groups: dict[tuple[date, str], list[tuple[FinancialsFiling, datetime | None]]] = {}
    for raw in rows:
        if raw.get("type") != _FINANCIALS_TYPE:
            continue
        try:
            basis = _basis(raw.get("consolidated"))
            url = raw.get("xbrl")
            if basis is None or not url or not str(url).startswith("http"):
                raise ValueError("bad basis or url")
            broadcast = _timestamp(raw.get("broadcast_Date"))
            revised_at = _timestamp(raw.get("revised_Date"))
            stamp = broadcast or revised_at
            if stamp is None:
                raise ValueError("no usable broadcast_Date or revised_Date")
            filing = FinancialsFiling(
                symbol=raw["symbol"],
                period_end=datetime.strptime(raw["qe_Date"], "%d-%b-%Y").date(),
                basis=basis,
                audited=_audited(raw.get("audited")),
                filed_at=stamp,
                xbrl_url=url,
                format=detect_format(url),
                revised=revised_at is not None,
            )
        except (KeyError, TypeError, ValueError) as e:
            log.warning("skipping malformed integrated-filing row: %s: %s", type(e).__name__, e)
            continue
        groups.setdefault((filing.period_end, filing.basis), []).append((filing, broadcast))

    out: list[FinancialsFiling] = []
    for group in groups.values():
        latest = max((f for f, _ in group), key=lambda f: f.filed_at)
        broadcasts = [b for _, b in group if b is not None]
        first = min(broadcasts) if broadcasts else min(f.filed_at for f, _ in group)
        out.append(latest.model_copy(update={"filed_at": first}))
    return sorted(out, key=lambda f: (-f.period_end.toordinal(), f.basis))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _quarter_context(root: ET.Element, period_end: date) -> tuple[str, date]:
    for ctx in root.findall(f"{_XBRLI}context"):
        if (
            ctx.find(f"{_XBRLI}scenario") is not None
            or ctx.find(f"{_XBRLI}entity/{_XBRLI}segment") is not None
        ):
            continue
        start = ctx.findtext(f"{_XBRLI}period/{_XBRLI}startDate")
        end = ctx.findtext(f"{_XBRLI}period/{_XBRLI}endDate")
        if not start or not end:
            continue
        try:
            s, e = date.fromisoformat(start.strip()), date.fromisoformat(end.strip())
        except ValueError:
            continue
        if e == period_end and 80 <= (e - s).days <= 100:
            return ctx.get("id", ""), s
    raise XbrlError(f"no 3-month context ending {period_end}")


def parse_xbrl(xml: bytes, *, format_hint: XbrlFormat | None = None) -> QuarterFinancials:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise XbrlError(f"malformed XBRL: {e}") from e

    def text_fact(name: str) -> str | None:
        for el in root:
            if _local(el.tag) == name and el.text and el.text.strip():
                return el.text.strip()
        return None

    end_text = text_fact("DateOfEndOfReportingPeriod")
    if not end_text:
        raise XbrlError("missing DateOfEndOfReportingPeriod")
    try:
        period_end = date.fromisoformat(end_text)
    except ValueError as e:
        raise XbrlError(f"bad DateOfEndOfReportingPeriod {end_text!r}") from e

    ctx_id, period_start = _quarter_context(root, period_end)

    facts: dict[str, float] = {}
    for el in root:
        if el.get("contextRef") != ctx_id or el.get("unitRef") != "INR":
            continue
        name = _local(el.tag)
        if name in facts:
            continue
        try:
            facts[name] = float((el.text or "").strip())
        except ValueError:
            continue

    basis = _basis(text_fact("NatureOfReportStandaloneConsolidated"))
    if basis is None:
        raise XbrlError("missing or unknown NatureOfReportStandaloneConsolidated")
    symbol = text_fact("Symbol")
    if not symbol:
        raise XbrlError("missing Symbol")

    fmt = format_hint
    if fmt is None:
        if "InterestExpended" in facts:
            fmt = "bank"
        elif "ImpairmentOnFinancialInstruments" in facts:
            fmt = "nbfc"
        else:
            fmt = "indas"

    return QuarterFinancials(
        symbol=symbol,
        period_start=period_start,
        period_end=period_end,
        basis=basis,
        format=fmt,
        audited=_audited(text_fact("WhetherResultsAreAuditedOrUnaudited")),
        facts=facts,
    )
