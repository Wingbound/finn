"""Paid-tier list prices, used only to report what free-tier usage would have cost."""

import logging
from functools import cache

log = logging.getLogger(__name__)

# USD per 1M tokens (input, output); output includes reasoning/thinking tokens.
# Checked 2026-11-09 against console.groq.com/docs/models and aistudio.google.com/docs/pricing.
LIST_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
    "gemini-3.8-flash": (0.75, 3.75),  # promo price through 2026-12-31; 1.50/7.50 after
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
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
