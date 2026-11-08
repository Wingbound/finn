"""Classification pipeline: rules first, LLM for the leftovers, default as last resort."""

from __future__ import annotations

import sqlite3

from finn import db
from finn.classify import default_classification
from finn.classify.llm import classify_batch_llm
from finn.classify.rules import classify_rules
from finn.llm import LLMRouter
from finn.models import Classification


def classify_pending(conn: sqlite3.Connection, router: LLMRouter | None) -> dict[str, int]:
    """Classify every unclassified filing, persist, and return counts by source.

    Filings left at the default by an earlier run go through the rules again, so rule
    improvements reach them without API keys. With a router, the ones the rules still miss
    are retried on the LLM too. Without one they are left as they are (and not counted).
    """
    results: dict[str, Classification] = {}
    leftovers = []
    for f in db.default_classified_filings(conn):
        c = classify_rules(f)
        if c is not None:
            results[f.seq_id] = c
        elif router is not None:
            leftovers.append(f)
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
            results[f.seq_id] = default_classification()
    db.save_classifications(conn, results)
    counts = {"rules": 0, "llm": 0, "default": 0}
    for c in results.values():
        counts[c.by] += 1
    return counts
