"""Enrichment of stored filings (results cards, grounded people, ...)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EnrichResult:
    done: int = 0  # filings enriched and saved
    empty: int = 0  # filings with nothing to enrich (saved so they are not retried)
    failed: dict[str, str] = field(default_factory=dict)  # seq_id -> why; not saved, retried
