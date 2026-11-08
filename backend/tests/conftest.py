import pytest

from finn import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "finn.sqlite")
    db.init_db(c)
    yield c
    c.close()
