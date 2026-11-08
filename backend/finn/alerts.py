"""Configurable alert engine: volume spikes, price moves, material filings."""

from __future__ import annotations

from finn.models import IST, Alert, PriceBar, Rules, Story, SymbolOverride

MIN_VOLUME_HISTORY = 10
IMPORTANT_FLOOR = 45
ALERT_TIERS = {"critical", "important"}
MAX_MESSAGE = 140


def evaluate_prices(history: dict[str, list[PriceBar]], rules: Rules, sessions: int = 5) -> list[Alert]:
    alerts: list[Alert] = []
    for symbol, raw in history.items():
        ov = rules.overrides.get(symbol, SymbolOverride())
        if ov.muted:
            continue
        vol_mult = ov.volume_multiple if ov.volume_multiple is not None else rules.volume_multiple
        move_pct = ov.price_move_pct if ov.price_move_pct is not None else rules.price_move_pct
        bars = sorted(raw, key=lambda b: b.date)
        for i in range(max(0, len(bars) - sessions), len(bars)):
            bar = bars[i]
            prior = bars[max(0, i - rules.lookback) : i]
            if len(prior) >= MIN_VOLUME_HISTORY:
                avg = sum(b.volume for b in prior) / len(prior)
                if avg > 0:
                    ratio = bar.volume / avg
                    if ratio >= vol_mult:
                        alerts.append(
                            Alert(
                                kind="volume",
                                symbol=symbol,
                                date=bar.date,
                                value=ratio,
                                threshold=vol_mult,
                                message=f"{symbol} traded {ratio:.1f}× its 20-day average volume",
                            )
                        )
            if prior and prior[-1].close > 0:
                pct = (bar.close / prior[-1].close - 1) * 100
                if abs(pct) >= move_pct:
                    direction = "up" if pct > 0 else "down"
                    alerts.append(
                        Alert(
                            kind="price",
                            symbol=symbol,
                            date=bar.date,
                            value=pct,
                            threshold=move_pct,
                            message=f"{symbol} {direction} {abs(pct):.1f}% on the day",
                        )
                    )
    alerts.sort(key=lambda a: a.symbol)
    alerts.sort(key=lambda a: a.date, reverse=True)
    return alerts


def evaluate_filings(stories: list[Story], rules: Rules) -> list[Alert]:
    alerts: list[Alert] = []
    for s in stories:
        if s.category not in rules.categories or s.tier not in ALERT_TIERS:
            continue
        ov = rules.overrides.get(s.symbol)
        if ov and ov.muted:
            continue
        alerts.append(
            Alert(
                kind="filing",
                symbol=s.symbol,
                date=s.latest_at.astimezone(IST).date(),
                value=s.score,
                threshold=IMPORTANT_FLOOR,
                message=s.headline.filing.subject[:MAX_MESSAGE],
                story_id=s.id,
            )
        )
    alerts.sort(key=lambda a: a.symbol)
    alerts.sort(key=lambda a: a.date, reverse=True)
    return alerts
