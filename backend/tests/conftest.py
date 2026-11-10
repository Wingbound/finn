import pytest

from finn import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "finn.sqlite")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _fresh_build_limits():
    """Each test starts with no builds counted against the per-instance limits."""
    from finn.api import main as api_main

    api_main._inflight.clear()
    api_main._recent.clear()
    yield
    api_main._inflight.clear()
    api_main._recent.clear()


@pytest.fixture(autouse=True)
def _no_live_nse_prices(monkeypatch):
    """Tests never call NSE's MCP server: the refresh sees it return nothing, so the Yahoo
    path (patched per test) behaves as it always has. tests/test_nse_prices.py tests the
    client itself against recorded responses."""
    import scripts.refresh as refresh_mod
    from finn.ingest.nse_mcp import NseResult

    # No hasattr guard: if the import is renamed, this fails loudly instead of letting tests
    # reach the network.
    monkeypatch.setattr(refresh_mod, "fetch_nse_eod", lambda holdings, **k: NseResult([], {}, {}))
