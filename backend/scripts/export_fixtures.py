"""Write the frontend's API fixtures from a stored snapshot.

Calls the real FastAPI app in-process against a private copy of the database, with the
clock pinned to two hours after the newest filing, so the output is deterministic and
matches what the deployed API serves from the same snapshot.

    uv run python scripts/export_fixtures.py --db seed/finn.sqlite --out ../frontend/tests/fixtures
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from finn import db
from finn.api.deps import get_conn, get_now
from finn.api.main import _done, _sse, app
from finn.models import IST, Rules
from finn.portfolio import load_portfolio
from finn.research.cite import dossier_citations


def _write(out: Path, name: str, payload: object) -> None:
    text = (
        payload if isinstance(payload, str) else json.dumps(payload, indent=1, ensure_ascii=False)
    )
    (out / name).write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
    print(f"  {name}")


def _ok(resp) -> Any:
    if resp.status_code != 200:
        raise SystemExit(
            f"{resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text}"
        )
    return resp.json()


def export(db_path: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "finn.sqlite"
        src = sqlite3.connect(db_path)  # the backup API copies a consistent snapshot, WAL included
        dst = sqlite3.connect(work)
        src.backup(dst)
        src.close()
        dst.close()

        conn0 = db.connect(work)
        db.init_db(conn0)  # an older snapshot may predate some tables
        symbols = [h.symbol for h in load_portfolio()]
        latest = db.latest_filed_at(conn0, symbols)
        dossiers = db.list_dossiers(conn0)
        conn0.close()
        if latest is None:
            raise SystemExit("the snapshot has no filings")
        now = (latest + timedelta(hours=2)).astimezone(IST)

        def conn_dep() -> Iterator[sqlite3.Connection]:
            c = db.connect(work)
            try:
                yield c
            finally:
                c.close()

        app.dependency_overrides[get_conn] = conn_dep
        app.dependency_overrides[get_now] = lambda: now
        try:
            # no `with`: the lifespan would seed the configured DB_PATH, which we never touch
            client = TestClient(app)
            _write(out, "meta.json", {"now": now.isoformat(), "source_db": db_path.name})
            _write(out, "health.json", _ok(client.get("/health")))
            _write(out, "portfolio.json", _ok(client.get("/portfolio")))
            _write(
                out,
                "alerts.json",
                _ok(client.post("/alerts", json=Rules().model_dump(mode="json"))),
            )

            d24 = _ok(client.post("/digest", json={"hours": 24}))
            _write(out, "digest-24h.json", d24)
            d7 = _ok(client.post("/digest", json={"hours": 168}))
            _write(out, "digest-7d.json", d7)
            _write(
                out,
                "digest-everything-7d.json",
                _ok(client.post("/digest", json={"hours": 168, "floor": "everything"})),
            )
            empty_end = datetime(2020, 1, 1, tzinfo=IST).isoformat()
            _write(
                out,
                "digest-empty.json",
                _ok(client.post("/digest", json={"hours": 24, "end": empty_end})),
            )

            # results cards: every story symbol with one on file, so bank and NBFC formats appear
            seen: set[str] = set()
            for st in d7["stories"]:
                sym = st["symbol"]
                if st.get("results") and sym not in seen:
                    seen.add(sym)
                    _write(out, f"results-{sym}.json", _ok(client.get(f"/results/{sym}")))
            if d7["stories"]:
                seq = d7["stories"][0]["headline"]["filing"]["seq_id"]
                subs = "&".join(f"subscribed={c}" for c in sorted(Rules().categories))
                _write(out, "filing.json", _ok(client.get(f"/filings/{seq}?{subs}")))

            _write(out, "research-list.json", _ok(client.get("/research")))
            for d in dossiers:
                sym = d.symbol
                _write(out, f"dossier-{sym}.json", _ok(client.get(f"/research/{sym}")))
                cites = [c for _, c in dossier_citations(d) if c.source_id != "FACTS"]
                if cites:
                    c = cites[0]
                    page = _ok(client.get(f"/research/{sym}/source/{c.source_id}/{c.page}"))
                    _write(out, f"source-{sym}.json", {"citation": c.model_dump(), **page})
            if dossiers:
                # A build stream as the API frames it: progress, a keep-alive comment, done.
                d = dossiers[0]
                frames = [
                    _sse("progress", {"msg": f"Resolving {d.symbol} on screener"}),
                    _sse(
                        "progress",
                        {
                            "msg": "Found 21 transcripts (reading the latest 4) and 15 annual report(s) (reading the latest)"
                        },
                    ),
                    ": ping\n\n",
                    _sse("progress", {"msg": "Extracting guidance from the latest call"}),
                    _sse(*_done(d)),
                ]
                _write(out, f"build-{d.symbol}.sse", "".join(frames))
                _write(
                    out,
                    "build-error.sse",
                    _sse("progress", {"msg": "Resolving ZZZZ on screener"})
                    + _sse("error", {"detail": "ZZZZ not found on screener"}),
                )
                _write(
                    out,
                    "build-incomplete.sse",
                    _sse("progress", {"msg": f"Resolving {d.symbol} on screener"}) + ": ping\n\n",
                )
        finally:
            app.dependency_overrides.clear()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    return export(args.db, args.out)


if __name__ == "__main__":
    sys.exit(main())
