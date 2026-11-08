"""Paid-tier list prices, used only to report what free-tier usage would have cost."""

import logging
from functools import cache

log = logging.getLogger(__name__)

# USD per 1M tokens (input, output).
# UNVERIFIED (from public docs, 2026-11-08) — verify via list-models when keys arrive
LIST_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "llama-3.1-8b-instant": (0.05, 0.08),  # Groq page says "contact sales"; approximate
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "gemini-3.8-flash": (0.75, 3.75),  # promo price through 2026-12-31; 1.50/7.50 after
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),
}


@cache
def _warn_unpriced(model: str) -> None:  # once per model, not once per call
    log.warning("no list price for model %r; its calls are logged at $0", model)


def list_price_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in LIST_PRICES_PER_MTOK:
        _warn_unpriced(model)
        return 0.0
    price_in, price_out = LIST_PRICES_PER_MTOK[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
