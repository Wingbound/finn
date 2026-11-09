from scripts import eval_results
from scripts.eval_results import evaluate_offline, render


def _rows(symbol):
    return [r for r in evaluate_offline() if r.symbol == symbol]


def test_eval_offline_tatasteel_all_match():
    rows = _rows("TATASTEEL")
    assert {r.metric for r in rows} == {"revenue", "ebitda", "pbt+assoc", "pat"}
    assert all(r.match for r in rows), [r for r in rows if not r.match]


def test_eval_offline_skips_basis_mismatch():
    for sym in ("IDFCFIRSTB", "BAJFINANCE"):
        rows = _rows(sym)
        assert len(rows) == 1 and rows[0].match is None
        assert "basis mismatch" in rows[0].note


def test_within_tolerance_rule():
    assert eval_results.within(1000.0, 1009.0)  # < 1%
    assert eval_results.within(10.0, 10.9)  # < 1 cr
    assert not eval_results.within(1000.0, 1020.0)


def test_render_has_table_rates_and_misses():
    out = render(evaluate_offline())
    assert "| symbol | basis | metric | ours | screener | diff % | match |" in out
    assert "skipped: basis mismatch" in out
    assert "TATASTEEL" in out
