from finn.enrich.results import card_for
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


def _cards():
    conn = eval_results._fixture_conn()
    return conn, {s: card_for(conn, s)[0] for s in ("TATASTEEL", "IDFCFIRSTB", "BAJFINANCE")}


def test_pairs_reference_metrics_build_card_produces():
    _conn, cards = _cards()
    for sym, card in cards.items():
        keys = {m.key for m in card.metrics}
        if card.format == "indas":
            keys.add("pbt+assoc")
        assert {k for k, _ in eval_results.PAIRS[card.format]} <= keys, sym
    assert {c.format for c in cards.values()} == {"indas", "bank", "nbfc"}


def test_bank_compare_runs_when_basis_matches():
    conn = eval_results._fixture_conn()
    html = (eval_results.FIX / "screener" / "IDFCFIRSTB_consolidated_quarters.html").read_text()
    rows = eval_results.compare(conn, "IDFCFIRSTB", "standalone", html)
    assert {r.metric for r in rows} == {"interest_earned", "pbt", "pat"}
    assert all(r.note != "missing value" and r.match is not None for r in rows)
