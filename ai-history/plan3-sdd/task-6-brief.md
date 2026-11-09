### Task 6: Synthesis — snapshot and bull vs bear, all cited

**Files:**
- Create: `backend/finn/research/synthesis.py`
- Modify: `backend/finn/models.py` (`Snapshot`, `Point`)
- Test: `backend/tests/test_research_synthesis.py`

**Interfaces:**
```python
class Point(BaseModel):
    text: str               # ≤ 30 words
    citation: Citation

class Snapshot(BaseModel):
    summary: list[Point]    # 2–4 sentences about what the company does and its segments, each cited
def snapshot(router, sources: list[Source]) -> Snapshot | None
    # input: AR pages (if any) + T1's first 4 pages (management's opening remarks), tagged
def bull_bear(router, sources: list[Source], ledger: Ledger, trajectory: Trajectory, health: BalanceSheetHealth) -> tuple[list[Point], list[Point]]
    # input: ledger summary + flags + tagged excerpts; up to 3 each; ungrounded points dropped
```
- **Validation:** each point's quote must `locate` in its claimed source, or the point is dropped. The text must pass `numbers_grounded(text, quote + computed-facts string)`. Numbers may come from the quote or from the computed analytics, which are passed to the model as an explicit "FACTS" block that is also used for grounding.
- **Router task:** `reason`, one call each, so at most 2 calls.
- **On LLMError:** None / ([], []), with a note.

- [ ] **Step 1: Write failing tests:**
  - A FakeRouter snapshot with one real and one invented quote keeps only the real one.
  - A bull point with a number taken from the FACTS block is kept.
  - A bull point with an invented number is dropped.
  - A cap of 3 each.
  - An `LLMError` gives None and empty lists.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Commit** `feat(research): cited snapshot and bull/bear`.

---

