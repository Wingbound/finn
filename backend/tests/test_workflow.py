"""The scheduled refresh: the workflow file and the seed compactor it runs."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import yaml

from finn import db

BACKEND = Path(__file__).resolve().parent.parent
WORKFLOW = BACKEND.parent / ".github" / "workflows" / "refresh.yml"


def _wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def test_workflow_runs_daily_at_six_ist_and_on_demand():
    wf = _wf()
    on = wf.get("on", wf.get(True))  # PyYAML reads a bare `on:` key as True
    assert on["schedule"] == [{"cron": "30 0 * * *"}]
    assert "workflow_dispatch" in on
    assert wf["permissions"] == {"contents": "write"}
    assert wf["concurrency"]["group"] == "refresh"


def test_workflow_keys_come_from_secrets_only():
    text = WORKFLOW.read_text()
    assert "${{ secrets.GEMINI_API_KEY }}" in text and "${{ secrets.GROQ_API_KEY }}" in text
    for line in text.splitlines():
        if "API_KEY:" in line:
            assert "${{ secrets." in line, line


def test_nothing_ingested_fails_without_committing():
    steps = _wf()["jobs"]["refresh"]["steps"]
    run = next(s for s in steps if s.get("id") == "refresh")["run"]
    assert '"$code" -eq 2' in run and "exit 1" in run
    commit = next(s for s in steps if "git commit" in s.get("run", ""))
    assert "git diff --quiet" in commit["run"]
    # a failed step stops the job, so the commit step never runs after exit 2
    assert "if" not in commit or "always()" not in commit["if"]


def test_workflow_paths_exist():
    text = WORKFLOW.read_text()
    for rel in ("scripts/refresh.py", "scripts/compact_seed.py", "seed/finn.sqlite"):
        assert rel in text
        assert (BACKEND / rel).exists(), rel


def test_compact_seed_drops_document_caches_and_checks_size(tmp_path):
    from scripts.compact_seed import main

    path = tmp_path / "finn.sqlite"
    shutil.copyfile(BACKEND / "seed" / "finn.sqlite", path)
    conn = db.connect(path)
    db.init_db(conn)
    conn.execute("INSERT INTO doc_text (url, fetched_at, chars, text) VALUES ('u', 'now', 3, 'abc')")
    conn.execute("INSERT INTO doc_pages (url, page, text) VALUES ('u', 1, 'p')")
    conn.commit()
    conn.close()
    assert main([str(path), "--max-mb", "20"]) == 0
    c = sqlite3.connect(path)
    assert c.execute("SELECT COUNT(*) FROM doc_text").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM doc_pages").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM filings").fetchone()[0] > 0
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    c.close()
    assert main([str(path), "--max-mb", "0.001"]) == 1  # over the cap
