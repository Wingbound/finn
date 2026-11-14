"""scripts/seed_changed.py: the refresh commits a new snapshot only when its data changed (Plan 8)."""

import sqlite3
from pathlib import Path

from scripts.seed_changed import main

SCHEMA = """
CREATE TABLE filings(seq_id TEXT PRIMARY KEY, symbol TEXT, subject TEXT);
CREATE TABLE prices(symbol TEXT, date TEXT, close REAL, PRIMARY KEY(symbol, date));
CREATE TABLE enrichments(seq_id TEXT, kind TEXT, payload_json TEXT, PRIMARY KEY(seq_id, kind));
CREATE TABLE financials(symbol TEXT, period_end TEXT, basis TEXT, PRIMARY KEY(symbol, period_end, basis));
CREATE TABLE dossiers(symbol TEXT PRIMARY KEY, built_at TEXT, payload_json TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE llm_calls(id INTEGER PRIMARY KEY, ts TEXT);
"""


def make(path: Path, *, meta_ts: str = "2026-11-13T12:00", extra_sql: str = "") -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executescript(
        """
        INSERT INTO filings VALUES ('1', 'TCS', 'Results');
        INSERT INTO prices VALUES ('TCS', '2026-11-12', 4000.0);
        INSERT INTO enrichments VALUES ('1', 'brief', '{}');
        INSERT INTO financials VALUES ('TCS', '2026-09-30', 'consolidated');
        INSERT INTO dossiers VALUES ('TCS', '2026-11-10', '{}');
        """
    )
    conn.execute("INSERT INTO meta VALUES ('filings_as_of', ?)", (meta_ts,))
    conn.execute("INSERT INTO llm_calls(ts) VALUES (?)", (meta_ts,))
    conn.executescript(extra_sql)
    conn.commit()
    conn.close()
    return path


def test_new_timestamps_alone_are_not_a_change(tmp_path):
    before = make(tmp_path / "a.sqlite")
    after = make(tmp_path / "b.sqlite", meta_ts="2026-11-14T09:47")
    assert main([str(before), str(after)]) == 1


def test_a_new_filing_is_a_change(tmp_path):
    before = make(tmp_path / "a.sqlite")
    after = make(
        tmp_path / "b.sqlite", extra_sql="INSERT INTO filings VALUES ('2', 'TCS', 'Dividend');"
    )
    assert main([str(before), str(after)]) == 0


def test_a_changed_price_is_a_change(tmp_path):
    before = make(tmp_path / "a.sqlite")
    after = make(tmp_path / "b.sqlite", extra_sql="UPDATE prices SET close = 4010.0;")
    assert main([str(before), str(after)]) == 0


def test_a_missing_snapshot_counts_as_changed(tmp_path):
    after = make(tmp_path / "b.sqlite")
    assert main([str(tmp_path / "missing.sqlite"), str(after)]) == 0
