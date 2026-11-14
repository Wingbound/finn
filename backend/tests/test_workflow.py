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


def test_workflow_runs_every_three_hours_on_weekdays_and_on_demand():
    wf = _wf()
    on = wf.get("on", wf.get(True))  # PyYAML reads a bare `on:` key as True
    # Plan 8: 06:47-21:47 IST every 3 hours on weekdays, once at weekends, off the hour
    assert on["schedule"] == [{"cron": "17 1,4,7,10,13,16 * * 1-5"}, {"cron": "17 4 * * 0,6"}]
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
    assert "2)" in run and "exit 1" in run.split("2)")[1].split(";;")[0]
    commit = next(s for s in steps if "git commit" in s.get("run", ""))
    # Plan 8: commits only when the content tables changed, and rebases before pushing
    assert "scripts/seed_changed.py" in commit["run"] and "before.sqlite" in run
    assert commit["run"].index("git pull --rebase") < commit["run"].index("git push")
    # a failed step stops the job, so the commit step never runs after exit 2
    assert "if" not in commit or "always()" not in commit["if"]


def test_workflow_paths_exist():
    text = WORKFLOW.read_text()
    for rel in (
        "scripts/refresh.py",
        "scripts/compact_seed.py",
        "scripts/seed_changed.py",
        "seed/finn.sqlite",
    ):
        assert rel in text
        assert (BACKEND / rel).exists(), rel


def test_compact_seed_drops_document_caches_and_checks_size(tmp_path):
    from scripts.compact_seed import main

    path = tmp_path / "finn.sqlite"
    shutil.copyfile(BACKEND / "seed" / "finn.sqlite", path)
    conn = db.connect(path)
    db.init_db(conn)
    conn.execute(
        "INSERT INTO doc_text (url, fetched_at, chars, text) VALUES ('u', 'now', 3, 'abc')"
    )
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


def test_only_clean_or_partial_refreshes_go_on_to_commit():
    """Plan 5 review I2: 2 (nothing ingested), 4 (crash) and signals (137, 143) all fail the job."""
    steps = _wf()["jobs"]["refresh"]["steps"]
    run = next(s for s in steps if s.get("id") == "refresh")["run"]
    assert 'case "$code" in' in run
    assert "0|1)" in run
    assert "*)" in run and run.count("exit 1") >= 2
