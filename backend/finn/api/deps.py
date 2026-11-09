"""Request-scoped dependencies (overridden in tests)."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from finn import db
from finn.api.seed import copy_seed_if_empty
from finn.config import Settings, get_settings
from finn.models import IST

_seed_lock = threading.Lock()
_seeded: set[Path] = set()


def ensure_seeded(settings: Settings) -> None:
    """Copy the committed snapshot into an empty store, once per store per process.

    Called on every request, because a serverless platform may never run the ASGI lifespan;
    the lock makes concurrent first requests on a cold instance wait for one copy.
    """
    path = Path(settings.db_path)  # type: ignore[arg-type]
    if path in _seeded:
        return
    with _seed_lock:
        if path not in _seeded:
            copy_seed_if_empty(path, settings.seed_path)
            _seeded.add(path)


def get_conn() -> Iterator[sqlite3.Connection]:
    # One connection per request: sqlite3 connections are bound to their creating thread.
    settings = get_settings()
    ensure_seeded(settings)
    conn = db.connect(settings.db_path)
    try:
        db.init_db(conn)
        yield conn
    finally:
        conn.close()


def get_now() -> datetime:
    return datetime.now(IST)
