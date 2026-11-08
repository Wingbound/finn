"""Batched LLM fallback classifier for filings the rules leave ambiguous."""

from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from finn.classify.rules import SUMMARY_CHARS
from finn.llm import LLMError, LLMRouter
from finn.models import CATEGORIES, Classification, Filing

LLM_CONFIDENCE = 0.7

SYSTEM_PROMPT = """\
You classify Indian stock-exchange (NSE) corporate filings into exactly one category.
Categories:
- results: Quarterly/annual results, the board meeting approving them, results decks and shareholder letters, and ads confirming results were published.
- mna: Any acquisition, merger, demerger, or joint venture - including investing in a subsidiary, or selling a stake in one.
- fund_raise: Raising money from outside investors - rights issues, QIPs, preferential allotments, buybacks, or debt like commercial paper.
- management_change: Any change at the top - a CEO, CFO, MD, or director joining, resigning, or retiring.
- litigation: Lawsuits, regulatory orders, fines, warnings, or insolvency/restructuring proceedings.
- insider_trading: A promoter or insider buying/selling their own personal shareholding.
- earnings_call: Anything about the investor conference call - the notice, the transcript, or the recording link.
- investor_meetings: One-on-one or small-group meetings with specific investors/funds, or attending an investor conference.
- credit_rating: A rating agency assigning, upgrading, downgrading, or reaffirming a credit rating.
- dividend: A cash dividend being declared, with its record date.
- bonus_split: A bonus issue or stock split - share count changes but no cash comes to you.
- capex: Approving spend on a new plant, facility, or capacity expansion.
- press_release: General news - order wins, new products, partnerships, rumour clarifications - not covered by another category.
- postal_ballot: Shareholders voting by postal ballot - the notice and the result.
- agm_egm: Annual or Extraordinary General Meeting - the notice and the result.
- pledging: A promoter pledging, releasing, or changing the pledge status of shares.
- unclassified: Routine, low-relevance paperwork - ESOP allotments, compliance certificates, ESG reports, auditor appointments - that doesn't materially move the stock.
If a filing is routine paperwork, routine = unclassified.
The user message is a JSON list of {id, desc, subject, summary}.
Reply with JSON only: {"items":[{"id":"<id>","category":"<category>","subtype":"<short snake_case or null>"}]}
Include every id exactly once. subtype is optional."""


class _Item(BaseModel):
    id: str
    category: str
    subtype: str | None = None


class _Reply(BaseModel):
    items: list[_Item]


def _default() -> Classification:
    return Classification(category="unclassified", by="default", confidence=0.0)


def _payload(batch: list[Filing]) -> str:
    return json.dumps(
        [
            {
                "id": f.seq_id,
                "desc": f.nse_desc,
                "subject": f.subject,
                "summary": (f.nse_summary or "")[:SUMMARY_CHARS],
            }
            for f in batch
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _classify_one_batch(router: LLMRouter, batch: list[Filing]) -> dict[str, Classification]:
    out = {f.seq_id: _default() for f in batch}
    try:
        reply = _Reply.model_validate(router.complete_json("classify", SYSTEM_PROMPT, _payload(batch)))
    except (LLMError, ValidationError):
        return out
    for item in reply.items:
        if item.id in out and item.category in CATEGORIES:
            out[item.id] = Classification(
                category=item.category,  # type: ignore[arg-type]
                subtype=item.subtype or None,
                by="llm",
                confidence=LLM_CONFIDENCE,
            )
    return out


def classify_batch_llm(
    router: LLMRouter, filings: list[Filing], batch_size: int = 20
) -> dict[str, Classification]:
    """Classify filings via the LLM; failures default per item or per batch, never raise."""
    result: dict[str, Classification] = {}
    for i in range(0, len(filings), batch_size):
        result.update(_classify_one_batch(router, filings[i : i + batch_size]))
    return result
