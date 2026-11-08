"""Smoke test for the committed snapshot the API copies into an empty store."""

import sqlite3
from pathlib import Path

from finn.portfolio import load_portfolio

SEED = Path(__file__).resolve().parent.parent / "seed" / "finn.sqlite"


def test_committed_seed_is_a_usable_store():
    # immutable=1: read-only and no -wal/-shm files appear next to the committed seed
    conn = sqlite3.connect(f"{SEED.as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"filings", "prices", "meta", "llm_cache", "llm_calls"} <= tables
        symbols = {r[0] for r in conn.execute("SELECT DISTINCT symbol FROM prices")}
        assert len(symbols) == 18 and symbols == {h.symbol for h in load_portfolio()}
        assert conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0] > 0
        nulls = conn.execute("SELECT COUNT(*) FROM filings WHERE category IS NULL").fetchone()[0]
        assert nulls == 0
    finally:
        conn.close()
