"""Request-scoped dependencies (overridden in tests)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime

from finn import db
from finn.config import get_settings
from finn.models import IST


def get_conn() -> Iterator[sqlite3.Connection]:
    # One connection per request: sqlite3 connections are bound to their creating thread.
    conn = db.connect(get_settings().db_path)
    try:
        db.init_db(conn)
        yield conn
    finally:
        conn.close()


def get_now() -> datetime:
    return datetime.now(IST)
