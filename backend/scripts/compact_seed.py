"""Shrink a FINN store for committing: drop the document caches, fold the WAL, VACUUM.

Run: uv run python scripts/compact_seed.py seed/finn.sqlite [--max-mb 20]

Exits 1 when the result is still over --max-mb, so a scheduled job stops before committing
a snapshot that has grown out of hand.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Rebuilt on demand from the source PDFs; the dossiers and enrichments keep what they used.
CACHES = ("doc_pages", "doc_text")


def compact(path: Path) -> float:
    conn = sqlite3.connect(path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in CACHES:
            if t in tables:
                conn.execute(f"DELETE FROM {t}")  # fixed names from CACHES, never input
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("VACUUM")
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"integrity check failed: {ok}")
    finally:
        conn.close()
    return path.stat().st_size / 1_000_000


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", type=Path)
    ap.add_argument("--max-mb", type=float, default=20.0)
    args = ap.parse_args(argv)
    mb = compact(args.path)
    print(f"{args.path}: {mb:.1f} MB")
    if mb > args.max_mb:
        print(f"over the {args.max_mb} MB cap; not fit to commit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
