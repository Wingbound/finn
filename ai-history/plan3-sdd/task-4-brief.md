### Task 4: Guidance extraction — grounded promises

**Files:**
- Create: `backend/finn/research/guidance.py`, `backend/finn/research/cite.py`
- Modify: `backend/finn/models.py` (`Citation`, `Promise`)
- Test: `backend/tests/test_research_guidance.py`, `backend/tests/test_research_cite.py`

**Interfaces:**
```python
class Citation(BaseModel):
    source_id: str
    page: int               # 1-based
    quote: str

class Promise(BaseModel):
    id: str                 # f"{source_id}-{n}"
    citation: Citation
    topic: str              # short, e.g. "revenue growth", "deal wins", "margin"
    kind: Literal["quantitative", "qualitative"]
    metric: Literal["revenue_growth", "ebitda_margin", "pat_growth", "capex", "order_book", "volume_growth", "other"] | None
    target_low: float | None
    target_high: float | None
    unit: Literal["%", "cr", "x", "usd_mn", "usd_bn"] | None
    horizon: str | None     # as said: "Q3 FY27", "FY27", "H2 FY27", "next year", None
    made_in: str            # the source's quarter, e.g. "Q2 FY27"

# cite.py
def locate(quote: str, source: Source, hint_page: int | None) -> Citation | None
    # verbatim (normalize) on hint page, else first page that contains it; None if nowhere or < 6 words
def tagged_text(source: Source, max_chars: int = 60_000) -> str   # "[[p1]]\n…\n[[p2]]\n…", truncated at a page boundary

# guidance.py
MAX_PROMISES = 8
def extract_promises(router, source: Source) -> list[Promise]
```
- **Prompt (router task `extract_transcript`):**
  - Extract up to 8 forward-looking statements by management: guidance, targets, plans and expectations.
  - Each item has a verbatim `quote` copied exactly, and the `page` from the `[[pN]]` markers.
  - Fill `metric`, `target_low`, `target_high` and `unit` only when the quote states a number.
  - Analyst questions are not promises.
  - Reply as JSON `{"promises": [...]}`.
- **Validation:**
  - Type-check every field.
  - The quote must `locate` (at least 6 words, verbatim); otherwise drop the item.
  - The page is corrected by `locate`.
  - A non-null target number must appear in the quote (`numbers_grounded(str(target), quote)`), else the targets are set to None and kind becomes "qualitative".
  - Unknown metric or unit values become None.
  - Dedupe by normalized quote.
  - An `LLMError` gives `[]`, and the caller records a note.

- [ ] **Step 1: Write failing tests:**
  - `locate`: finds a real sentence from fixture T1 page 3 when hinted with the wrong page (returns the right page); a paraphrase gives None; a 5-word quote gives None.
  - `tagged_text` keeps page markers and truncates at a page boundary.
  - `extract_promises` with a FakeRouter reply holding:
    - a real quote from the fixture with a wrong page (kept, page fixed);
    - an invented quote (dropped);
    - a quote with target 25 where the quote has no "25" (kept as qualitative with targets None);
    - a duplicate (deduped);
    - an analyst question (kept only if the LLM returns it; that cannot be tested, so skip);
    - non-string fields (no crash).
  - `LLMError` gives `[]`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): grounded guidance extraction from transcripts`.

---

