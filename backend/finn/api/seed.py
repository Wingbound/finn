"""The committed snapshot the API serves, copied into an empty store."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)


def _has_filings(db_path: Path) -> bool:
    """Whether an existing SQLite file holds any filings (raises sqlite3.DatabaseError)."""
    conn = sqlite3.connect(db_path)
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='filings'"
        ).fetchone()
        return bool(table) and conn.execute("SELECT 1 FROM filings LIMIT 1").fetchone() is not None
    finally:
        conn.close()


def copy_seed_if_empty(db_path: Path, seed_path: Path) -> bool:
    """Start from the committed snapshot when the store is missing or has no filings.

    Scripts that open the serving DB create an empty one as a side effect, so "file exists"
    is not enough. A store with filings, or a file that isn't a readable database, is never
    overwritten.
    """
    if db_path.exists():
        try:
            if _has_filings(db_path):
                return False
        except sqlite3.DatabaseError as e:
            log.warning("not seeding %s: it is not a readable SQLite database (%s)", db_path, e)
            return False
    if not seed_path.exists():
        log.warning("seed snapshot %s not found; %s starts empty", seed_path, db_path)
        return False
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for sidecar in ("-wal", "-shm"):  # an old WAL would be replayed onto the copied seed
        Path(f"{db_path}{sidecar}").unlink(missing_ok=True)
    # Copy beside the target, then rename: a copy cut short (an instance recycled mid-copy)
    # leaves no truncated store behind for later requests to fail on.
    partial = db_path.with_name(f"{db_path.name}.seed-tmp")
    try:
        shutil.copyfile(seed_path, partial)
        partial.replace(db_path)
    finally:
        partial.unlink(missing_ok=True)
    return True
