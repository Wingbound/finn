from finn.portfolio import load_portfolio


def test_portfolio_has_18_unique():
    p = load_portfolio()
    syms = [h.symbol for h in p]
    assert len(p) == 18 and len(set(syms)) == 18


def test_yahoo_symbols():
    p = {h.symbol: h for h in load_portfolio()}
    assert p["M&M"].yahoo == "M&M.NS" and all(h.yahoo.endswith(".NS") for h in p.values())


def test_sector_and_size_mix():
    p = load_portfolio()
    assert len({h.sector for h in p}) >= 10
    assert {"mega", "large", "mid", "small"} <= {h.size for h in p}
