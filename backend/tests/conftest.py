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
