"""Classification pipeline: rules first, LLM for the leftovers, default as last resort."""

from __future__ import annotations

import sqlite3

from finn import db
from finn.classify.llm import classify_batch_llm
from finn.classify.rules import classify_rules
from finn.llm import LLMRouter
from finn.models import Classification


def classify_pending(conn: sqlite3.Connection, router: LLMRouter | None) -> dict[str, int]:
    """Classify every unclassified filing, persist, and return counts by source.

    With a router, filings left at the default by an earlier run (e.g. one without API
    keys) are retried on the LLM too; they already missed the rules.
    """
    results: dict[str, Classification] = {}
    leftovers = db.default_classified_filings(conn) if router is not None else []
    for f in db.unclassified_filings(conn):
        c = classify_rules(f)
        if c is None:
            leftovers.append(f)
        else:
            results[f.seq_id] = c
    if router is not None:
        results.update(classify_batch_llm(router, leftovers))
    else:
        for f in leftovers:
            results[f.seq_id] = Classification(category="unclassified", by="default", confidence=0.0)
    db.save_classifications(conn, results)
    counts = {"rules": 0, "llm": 0, "default": 0}
    for c in results.values():
        counts[c.by] += 1
    return counts
