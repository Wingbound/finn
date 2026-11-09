"""Build and store research dossiers.

Run: uv run python scripts/research.py PERSISTENT TCS [--out finn.sqlite]

Prints one line per symbol; always exits 0. A degraded rebuild (model unavailable, an
internal error or the deadline) never replaces a complete stored dossier; it prints a warning.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from finn import db
from finn.config import get_settings
from finn.ingest.screener import ScreenerError
from finn.llm import LLMRouter
from finn.research.pipeline import build_dossier, is_degraded


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--out", type=Path, default=None, help="SQLite store (default: settings)")
    args = ap.parse_args(argv)

    settings = get_settings()
    conn = db.connect(args.out or settings.db_path)
    db.init_db(conn)
    try:
        router = LLMRouter(conn, settings)
        for raw in args.symbols:
            sym = raw.upper()
            t0 = time.monotonic()
            try:
                d = build_dossier(
                    conn, sym, router, progress=lambda m: print(f"  {m}", file=sys.stderr)
                )
            except ScreenerError:
                print(f"{sym}: not found on screener")
                continue
            except Exception as e:  # noqa: BLE001 - one bad symbol must not stop the batch
                print(f"{sym}: failed ({type(e).__name__}: {e})")
                continue
            old = db.get_dossier(conn, sym)
            if is_degraded(d) and old is not None and not is_degraded(old):
                print(
                    f"{sym}: warning: rebuild incomplete ({'; '.join(d.notes)}); "
                    f"kept the stored dossier built {old.built_at:%Y-%m-%d %H:%M}"
                )
                continue
            db.save_dossier(conn, d)
            rows = d.ledger.rows if d.ledger else []
            print(
                f"{sym}: {len(rows)} ledger rows, {len(d.sources)} sources, "
                f"{d.cost['calls']} LLM calls, ${d.cost['usd_list_price']:.4f}, "
                f"{time.monotonic() - t0:.0f}s"
            )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
