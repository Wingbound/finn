"""Batched LLM fallback classifier for filings the rules leave ambiguous."""

from __future__ import annotations

import json
from collections.abc import Callable

from finn.classify import default_classification
from finn.classify.materiality import MODIFIERS
from finn.classify.rules import SUMMARY_CHARS, credit_subtype, management_subtype
from finn.llm import LLMError, LLMRouter
from finn.models import CATEGORIES, Classification, Filing

LLM_CONFIDENCE = 0.7

# Scoring looks subtypes up in MODIFIERS, so a free-form LLM subtype would silently score as
# "no modifier". For these categories the subtype comes from the rules' text helpers instead.
RULE_DERIVED_SUBTYPES: dict[str, Callable[[str], str | None]] = {
    "management_change": management_subtype,
    "credit_rating": credit_subtype,
}


def _llm_subtypes() -> dict[str, dict[str, str]]:
    """Allowlist for every other category: its MODIFIERS subtypes (subtype -> label)."""
    out: dict[str, dict[str, str]] = {}
    for (category, subtype), (_mult, label) in MODIFIERS.items():
        if category not in RULE_DERIVED_SUBTYPES:
            out.setdefault(category, {})[subtype] = label
    return out


LLM_SUBTYPES = _llm_subtypes()

_SUBTYPE_LINES = "\n".join(
    f"{category}: " + ", ".join(f"{sub} ({label})" for sub, label in subs.items())
    for category, subs in LLM_SUBTYPES.items()
)

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
Reply with JSON only: {"items":[{"id":"<id>","category":"<category>","subtype":"<subtype or null>"}]}
Include every id exactly once. subtype must be one of the values listed for the chosen
category below, or null when none fits or the category is not listed:
""" + _SUBTYPE_LINES


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


def _subtype(category: str, llm_subtype: object, f: Filing) -> str | None:
    """A subtype scoring understands: rule-derived, or the LLM's if allowlisted, else None."""
    derive = RULE_DERIVED_SUBTYPES.get(category)
    if derive is not None:
        return derive(f"{f.nse_desc} {f.subject} {(f.nse_summary or '')[:SUMMARY_CHARS]}")
    if not isinstance(llm_subtype, str):
        return None
    llm_subtype = llm_subtype.strip().lower()
    return llm_subtype if llm_subtype in LLM_SUBTYPES.get(category, {}) else None


def _parse_item(raw: object, batch: dict[str, Filing]) -> tuple[str, Classification] | None:
    """Validate one reply item; None if unusable (that filing then keeps its default)."""
    if not isinstance(raw, dict):
        return None
    item_id, category = raw.get("id"), raw.get("category")
    if isinstance(item_id, bool) or not isinstance(item_id, (str, int)):
        return None
    f = batch.get(str(item_id))
    if f is None or not isinstance(category, str) or category not in CATEGORIES:
        return None
    return f.seq_id, Classification(
        category=category,  # type: ignore[arg-type]
        subtype=_subtype(category, raw.get("subtype"), f),
        by="llm",
        confidence=LLM_CONFIDENCE,
    )


def _classify_one_batch(router: LLMRouter, batch: list[Filing]) -> dict[str, Classification]:
    out = {f.seq_id: default_classification() for f in batch}
    try:
        reply = router.complete_json("classify", SYSTEM_PROMPT, _payload(batch))
    except (LLMError, ValueError):  # ValueError: belt and braces; the pipeline never raises
        return out
    items = reply.get("items") if isinstance(reply, dict) else None
    if not isinstance(items, list):
        return out
    by_id = {f.seq_id: f for f in batch}
    for raw in items:
        parsed = _parse_item(raw, by_id)
        if parsed:
            out[parsed[0]] = parsed[1]
    return out


def classify_batch_llm(
    router: LLMRouter, filings: list[Filing], batch_size: int = 20
) -> dict[str, Classification]:
    """Classify filings via the LLM; failures default per item or per batch, never raise."""
    result: dict[str, Classification] = {}
    for i in range(0, len(filings), batch_size):
        result.update(_classify_one_batch(router, filings[i : i + batch_size]))
    return result
