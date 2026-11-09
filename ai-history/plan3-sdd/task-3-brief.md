### Task 3: Sources — transcripts and annual report with per-page text

**Files:**
- Create: `backend/finn/research/docs.py`
- Modify: `backend/finn/db.py` (`doc_pages` table and helpers), `backend/finn/models.py` (`Source`)
- Test: `backend/tests/test_research_docs.py`

**Interfaces:**
```python
class Source(BaseModel):
    id: str                 # "T1" (newest transcript) … "T4", "AR"
    kind: Literal["transcript", "annual_report"]
    title: str              # "Q2 FY27 earnings call (Oct 2026)" | "Annual Report 2026"
    quarter: str | None     # "Q2 FY27" for transcripts
    url: str
    pages: list[str]        # page text; pages[0] is page 1

class DocClient:            # httpx wrapper: browser UA; Referer "https://www.bseindia.com/" for bseindia hosts
    def fetch_bytes(self, url: str, max_bytes: int = 40_000_000) -> bytes   # raises DocError
class DocError(Exception): ...

def call_quarter(date_label: str) -> str     # "Oct 2026" -> "Q2 FY27"; "Jan 2026" -> "Q3 FY26"; "May 2026" -> "Q4 FY26"
def pdf_pages(pdf: bytes, max_pages: int | None = None) -> list[str]   # pypdf, never raises ([] on failure)
def get_pages(conn, client: DocClient, url: str, max_pages: int | None = None) -> list[str]   # cached in doc_pages
def collect_sources(conn, client, documents: dict, max_transcripts: int = 4, ar_pages: int = 40,
                    progress: Callable[[str], None] = lambda m: None) -> tuple[list[Source], list[str]]
    # returns (sources, notes); newest transcripts first; skips a transcript that fails to download or has no
    # text, with a note ("Oct 2026 transcript unavailable: …"); the AR is the newest annual report, first ar_pages pages
```
- `doc_pages(url TEXT, page INTEGER, text TEXT, PRIMARY KEY(url, page))`.
- A cached document is all its pages. Store a sentinel row `page = 0` with `text = ""` when extraction gave no pages, so it is not re-downloaded.

- [ ] **Step 1: Write failing tests:**
  - `call_quarter` across all months;
  - `pdf_pages` on `tests/fixtures/pdf/hello.pdf` gives 1 page containing "Ramesh Iyer";
  - garbage bytes give `[]`;
  - `max_pages` is respected;
  - `get_pages` caches: a second call does not fetch, and the empty sentinel also prevents a refetch;
  - `collect_sources`:
    - pre-seed `doc_pages` from `PERSISTENT_transcripts.json` for the four transcript URLs, and use the Task 1 `parse_documents(PERSISTENT_screener.html)` output;
    - 4 transcript Sources with ids T1..T4, newest first;
    - T1's title is "Q2 FY27 earnings call (Oct 2026)", and its `pages` length matches the fixture;
    - the AR fetch fails via a fake client raising `DocError`, so the notes mention the annual report and no AR source is returned;
  - a concall with `transcript_url=None` is skipped silently (not posted yet);
  - with only 2 transcripts available, 2 Sources are returned and nothing crashes.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): transcript and annual-report sources with cached page text`.

---

