"""screener.in quarterly-results table: a cross-check for our XBRL numbers, not a data source."""

from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self._in_head = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "thead":
            self._in_head = True
        elif tag == "tr" and not self._in_head:
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead":
            self._in_head = False
        elif tag in ("td", "th") and self._cell is not None:
            text = "".join(self._cell)
            if self._in_head:
                self.headers.append(" ".join(text.split()))
            elif self._row is not None:
                self._row.append(text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _label(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").replace("+", " ").split())


def _number(text: str) -> float | None:
    t = text.replace("\xa0", "").replace(",", "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _quarters_section(html: str) -> str:
    """The <section id="quarters"> block of a full page; the input itself if there is none."""
    m = re.search(r'<section\b[^>]*\bid="quarters"[^>]*>', html)
    if m is None:
        return html
    end = html.find("</section>", m.end())
    return html[m.start() : end if end != -1 else len(html)]


def _first_table(html: str) -> str:
    start = html.find("<table")
    if start == -1:
        return html
    end = html.find("</table>", start)
    return html[start : end + len("</table>") if end != -1 else len(html)]


def parse_quarters(html: str) -> dict[str, dict[str, float]]:
    """Column header ("Sep 2026") -> row label -> value in INR crore.

    Skips "%" rows, the "Raw PDF" row and empty or non-numeric cells.
    """
    p = _TableParser()
    p.feed(_first_table(_quarters_section(html)))
    cols = p.headers[1:]  # first <th> is the empty label column
    out: dict[str, dict[str, float]] = {c: {} for c in cols}
    for row in p.rows:
        if len(row) < 2:
            continue
        label = _label(row[0])
        if not label or label.endswith("%") or label == "Raw PDF":
            continue
        for col, cell in zip(cols, row[1:], strict=False):
            v = _number(cell)
            if v is not None:
                out[col][label] = v
    return out


def screener_url(symbol: str, basis: str) -> str:
    tail = "consolidated/" if basis == "consolidated" else ""
    return f"https://www.screener.in/company/{symbol}/{tail}"


def fetch_quarters(symbol: str, basis: str) -> str:
    """Live GET of the screener page for `basis`; used only by scripts/eval_results.py."""
    r = httpx.get(
        screener_url(symbol, basis),
        headers={"User-Agent": _UA},
        timeout=30,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.text
