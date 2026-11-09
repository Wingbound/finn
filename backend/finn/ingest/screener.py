"""screener.in quarterly-results table: a cross-check for our XBRL numbers, not a data source."""

from __future__ import annotations

import html as _html
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
    t = text.replace("\xa0", " ").replace("+", " ").strip()
    t = re.split(r"\s{2,}", t)[0]
    return " ".join(t.split())


def _number(text: str) -> float | None:
    t = text.replace("\xa0", "").replace(",", "").replace("%", "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _section(html: str, section_id: str) -> str:
    """The <section id=...> block of a full page; the input itself if there is none."""
    m = re.search(rf'<section\b[^>]*\bid="{re.escape(section_id)}"[^>]*>', html)
    if m is None:
        # a bare fragment (no <section> at all) is parsed whole; a full page lacking it is empty
        return html if "<section" not in html else ""
    end = html.find("</section>", m.end())
    return html[m.start() : end if end != -1 else len(html)]


def _first_table(html: str) -> str:
    start = html.find("<table")
    if start == -1:
        return html
    end = html.find("</table>", start)
    return html[start : end + len("</table>") if end != -1 else len(html)]


def parse_table(html: str, section_id: str, keep_pct: bool = True) -> dict[str, dict[str, float]]:
    """Column header ("Mar 2026") -> row label -> value, from the first table of a section.

    Skips the "Raw PDF" row and empty or non-numeric cells; "%" rows only when keep_pct
    is False (a value such as "16%" parses to 16.0).
    """
    p = _TableParser()
    p.feed(_first_table(_section(html, section_id)))
    cols = p.headers[1:]  # first <th> is the empty label column
    out: dict[str, dict[str, float]] = {c: {} for c in cols}
    for row in p.rows:
        if len(row) < 2:
            continue
        label = _label(row[0])
        if not label or label == "Raw PDF" or (not keep_pct and label.endswith("%")):
            continue
        for col, cell in zip(cols, row[1:], strict=False):
            v = _number(cell)
            if v is not None:
                out[col][label] = v
    return out


def parse_quarters(html: str) -> dict[str, dict[str, float]]:
    """Quarterly results, INR crore, without "%" rows."""
    return parse_table(html, "quarters", keep_pct=False)


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


SCREENER = "https://www.screener.in"


class ScreenerError(Exception):
    pass


def _http() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": _UA}, timeout=30, follow_redirects=True)


def search(query: str, client: httpx.Client | None = None) -> list[dict]:
    own = client is None
    c = client or _http()
    try:
        r = c.get(f"{SCREENER}/api/company/search/", params={"q": query, "v": 3, "fts": 1})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise ScreenerError(f"screener search failed: {e}") from e
    finally:
        if own:
            c.close()
    out = []
    for item in data if isinstance(data, list) else []:
        url = item.get("url") or ""
        m = re.match(r"/company/([^/]+)/", url)
        if m:
            out.append({"name": item.get("name", ""), "symbol": m.group(1), "url": url})
    return out


def fetch_company(symbol: str, client: httpx.Client | None = None) -> tuple[str, str]:
    """(html, basis): consolidated page if it has profit-loss data, else standalone."""
    own = client is None
    c = client or _http()
    try:
        for basis, tail in (("consolidated", "consolidated/"), ("standalone", "")):
            try:
                r = c.get(f"{SCREENER}/company/{symbol}/{tail}")
            except httpx.HTTPError as e:
                raise ScreenerError(f"screener fetch failed for {symbol}: {e}") from e
            if r.status_code == 404:
                continue
            if r.status_code >= 400:
                raise ScreenerError(f"screener returned {r.status_code} for {symbol}")
            if any(parse_table(r.text, "profit-loss").values()):  # headers alone are not data
                return r.text, basis
    finally:
        if own:
            c.close()
    raise ScreenerError(f"no screener financial data for {symbol}")


class _DocParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.annual: list[dict] = []
        self.concalls: list[dict] = []
        self._cur: dict | None = None
        self._href: str | None = None
        self._text: list[str] = []
        self._in_date = False
        self._in_li = False
        self._li_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "li":
            if "flex-gap-8" in cls:
                self._cur = {"date": "", "transcript_url": None, "ppt_url": None}
                self.concalls.append(self._cur)
            self._in_li = True
        elif tag == "div" and "ink-600" in cls and "nowrap" in cls and self._cur is not None:
            self._in_date = True
            self._text = []
        elif tag == "a":
            self._href = a.get("href")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._in_date and self._cur is not None:
            self._cur["date"] = " ".join("".join(self._text).split())
            self._in_date = False
        elif tag == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            href = _html.unescape(self._href)
            if self._cur is not None and text == "Transcript":
                self._cur["transcript_url"] = href
            elif self._cur is not None and text == "PPT":
                self._cur["ppt_url"] = href
            elif self._cur is None:
                m = re.fullmatch(r"Annual Report (\d{4})", text)
                if m:
                    self.annual.append({"year": int(m.group(1)), "url": href})
            self._href = None
        elif tag == "li":
            self._cur = None

    def handle_data(self, data: str) -> None:
        self._text.append(data)


def parse_documents(html: str) -> dict:
    p = _DocParser()
    p.feed(_section(html, "documents"))
    annual = sorted(p.annual, key=lambda d: -d["year"])
    return {"annual_reports": annual, "concalls": [c for c in p.concalls if c["date"]]}


def parse_name(html: str) -> str | None:
    m = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.DOTALL)
    if m is None:
        return None
    text = " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split())
    return text or None
