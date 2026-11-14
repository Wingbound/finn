"""Did a refresh change the snapshot's data? Exit 0 if it did, 1 if it didn't.

Run: uv run python scripts/seed_changed.py BEFORE.sqlite AFTER.sqlite

Only the content tables count. Timestamps in `meta`, the LLM call log and the LLM cache move on
every run, so a byte comparison would commit (and redeploy) a snapshot nothing new went into.
A missing or unreadable BEFORE counts as changed.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

CONTENT_TABLES = ("filings", "prices", "enrichments", "financials", "dossiers")


def fingerprint(path: Path) -> str | None:
    """sha256 over every content table, row by row in key order; None if unreadable."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in CONTENT_TABLES:
            h.update(f"\x00{table}\x00".encode())
            if table not in tables:
                h.update(b"<absent>")
                continue
            info = list(conn.execute(f"PRAGMA table_info({table})"))
            key = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]] or [r[1] for r in info]
            order = ", ".join(f'"{c}"' for c in key)
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                h.update(repr(row).encode())
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    args = ap.parse_args(argv)
    old, new = fingerprint(args.before), fingerprint(args.after)
    changed = old is None or old != new
    print("Snapshot data changed." if changed else "Snapshot data unchanged.")
    return 0 if changed else 1


if __name__ == "__main__":
    sys.exit(main())
