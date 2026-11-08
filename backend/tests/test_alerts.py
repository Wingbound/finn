from datetime import date, datetime, timedelta

from finn.alerts import evaluate_filings, evaluate_prices
from finn.models import (
    IST,
    Alert,
    Classification,
    Filing,
    PriceBar,
    Rules,
    ScoredFiling,
    Story,
    SymbolOverride,
)

START = date(2026, 10, 1)


def _series(symbol="TCS", n=25, last_vol=5_000_000, last_close=100.0, base_vol=5_000_000):
    bars = []
    for i in range(n):
        last = i == n - 1
        c = last_close if last else 100.0
        v = last_vol if last else base_vol
        bars.append(
            PriceBar(
                symbol=symbol,
                date=START + timedelta(days=i),
                open=c,
                high=c,
                low=c,
                close=c,
                volume=v,
            )
        )
    return bars


def test_volume_2_1x_triggers_at_2_not_2_5():
    hit = evaluate_prices({"TCS": _series(last_vol=10_500_000)}, Rules())
    assert [a.kind for a in hit] == ["volume"]
    assert hit[0].message == "TCS traded 2.1× its 20-day average volume"
    assert hit[0].threshold == 2.0
    miss = evaluate_prices({"TCS": _series(last_vol=10_500_000)}, Rules(volume_multiple=2.5))
    assert miss == []


def test_price_minus_5_2_triggers():
    out = evaluate_prices({"TCS": _series(last_close=94.8)}, Rules())
    assert [a.kind for a in out] == ["price"]
    assert out[0].message == "TCS down 5.2% on the day"
    assert round(out[0].value, 1) == -5.2


def test_price_up_message():
    out = evaluate_prices({"TCS": _series(last_close=106.0)}, Rules())
    assert out[0].message == "TCS up 6.0% on the day"


def test_override_beats_global():
    h = {"TCS": _series(last_vol=10_500_000, last_close=97.0)}
    assert evaluate_prices(h, Rules()) != [] and all(a.kind == "volume" for a in evaluate_prices(h, Rules()))
    rules = Rules(overrides={"TCS": SymbolOverride(volume_multiple=3.0, price_move_pct=2.0)})
    kinds = [a.kind for a in evaluate_prices(h, rules)]
    assert kinds == ["price"]


def test_muted_symbol_no_alerts():
    h = {"TCS": _series(last_vol=20_000_000, last_close=80.0)}
    rules = Rules(overrides={"TCS": SymbolOverride(muted=True)})
    assert evaluate_prices(h, rules) == []


def test_insufficient_history_no_volume_alert():
    out = evaluate_prices({"TCS": _series(n=10, last_vol=50_000_000)}, Rules())
    assert out == []  # only 9 prior bars
    out = evaluate_prices({"TCS": _series(n=11, last_vol=50_000_000)}, Rules())
    assert [a.kind for a in out] == ["volume"]


def test_price_window_limits_the_sessions_evaluated():
    h = {"TCS": _series(last_close=90.0)}  # 25 daily bars from 1 Oct; the move is on 25 Oct
    spike = START + timedelta(days=24)
    assert [a.date for a in evaluate_prices(h, Rules(), start=spike, end=spike)] == [spike]
    assert evaluate_prices(h, Rules(), end=spike - timedelta(days=1)) == []  # bar after end
    assert evaluate_prices(h, Rules(), start=spike + timedelta(days=1)) == []  # before start


def test_sorted_newest_first():
    a = _series("AAA", last_close=90.0)
    b = _series("BBB", last_close=90.0)
    out = evaluate_prices({"AAA": a, "BBB": b}, Rules())
    assert [(x.date, x.symbol) for x in out] == [(a[-1].date, "AAA"), (b[-1].date, "BBB")]


def _story(sid, category, tier, symbol="TCS", score=80):
    f = Filing(
        seq_id=sid,
        symbol=symbol,
        company="TCS Ltd",
        nse_desc="d",
        subject="S" * 200,
        filed_at=datetime(2026, 11, 6, 20, 0, tzinfo=IST),
    )
    sf = ScoredFiling(
        filing=f,
        cls=Classification(category=category, noise=False, by="rules", confidence=1.0),
        score=score,
        tier=tier,
        reasons=[],
    )
    return Story(
        id=sid,
        symbol=symbol,
        company="TCS Ltd",
        category=category,
        score=score,
        tier=tier,
        headline=sf,
        members=[sf],
        latest_at=f.filed_at,
    )


def test_filing_alerts_respect_categories():
    stories = [
        _story("a", "results", "critical"),
        _story("b", "dividend", "important", score=45),
        _story("c", "mna", "routine", score=30),
        _story("d", "litigation", "noise", score=0),
        _story("e", "pledging", "important", symbol="M&M", score=60),
    ]
    rules = Rules(overrides={"M&M": SymbolOverride(muted=True)})
    out = evaluate_filings(stories, rules)
    assert [a.story_id for a in out] == ["a"]
    a = out[0]
    assert isinstance(a, Alert) and a.kind == "filing"
    assert a.date == date(2026, 11, 6) and a.value == 80 and a.threshold == 45
    assert a.message == "S" * 140
