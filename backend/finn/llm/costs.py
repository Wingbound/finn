"""Paid-tier list prices, used only to report what free-tier usage would have cost."""

# USD per 1M tokens (input, output).
# UNVERIFIED (from public docs, 2026-11-08) — verify via list-models when keys arrive
LIST_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "llama-3.1-8b-instant": (0.05, 0.08),  # Groq page says "contact sales"; approximate
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "gemini-3.8-flash": (0.75, 3.75),  # promo price through 2026-12-31; 1.50/7.50 after
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),
}


def list_price_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = LIST_PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
