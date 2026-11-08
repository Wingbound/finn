"""Record real NSE responses as test fixtures (network). Run: uv run python scripts/record_fixtures.py"""

import json
import time
from datetime import date
from pathlib import Path

from finn.ingest.nse import NSEClient
from finn.portfolio import load_portfolio

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "nse"
START, END = date(2026, 10, 8), date(2026, 11, 8)
SINGLES = {"RELIANCE", "M&M", "TRENT"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = NSEClient()
    combined: list[dict] = []
    for holding in load_portfolio():
        items = client.fetch_announcements(holding.symbol, START, END)
        print(f"{holding.symbol}: {len(items)}")
        combined.extend(items)
        if holding.symbol in SINGLES:
            (OUT / f"{holding.symbol}.json").write_text(json.dumps(items, indent=1))
        time.sleep(0.5)
    (OUT / "portfolio_month.json").write_text(json.dumps(combined, indent=1))
    print(f"portfolio_month: {len(combined)}")


if __name__ == "__main__":
    main()
