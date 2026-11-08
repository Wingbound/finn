"""Shared test doubles. No network."""

import json
from pathlib import Path

from finn.ingest.nse import NSEUnavailable

FIXTURES = Path(__file__).parent / "fixtures"


class FakeNSE:
    def __init__(self, rows: dict[str, list[dict]], files: dict[str, bytes]):
        self.rows = rows
        self.files = files
        self.list_calls: list[str] = []
        self.byte_calls: list[str] = []

    def fetch_integrated_financials(self, symbol: str) -> list[dict]:
        self.list_calls.append(symbol)
        if symbol not in self.rows:
            raise NSEUnavailable(f"no rows for {symbol}")
        return self.rows[symbol]

    def fetch_bytes(self, url: str, max_bytes: int = 25_000_000) -> bytes:
        self.byte_calls.append(url)
        if url not in self.files:
            raise NSEUnavailable(f"no file for {url}")
        return self.files[url]


def tatasteel_fake() -> FakeNSE:
    rows = json.loads((FIXTURES / "nse" / "integrated_TATASTEEL.json").read_text())["data"]
    names = {
        "30-SEP-2026": "TATASTEEL_2026-09-30_cons.xml",
        "30-JUN-2026": "TATASTEEL_2026-06-30_cons.xml",
        "30-SEP-2025": "TATASTEEL_2025-09-30_cons.xml",
    }
    files = {
        r["xbrl"]: (FIXTURES / "xbrl" / names[r["qe_Date"].upper()]).read_bytes()
        for r in rows
        if r["consolidated"] == "Consolidated" and r["qe_Date"].upper() in names
    }
    return FakeNSE({"TATASTEEL": rows}, files)
