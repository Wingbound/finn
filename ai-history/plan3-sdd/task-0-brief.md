### Task 0: Plan 2 carry-overs

**Files:**
- Modify: `backend/finn/api/main.py`, `backend/finn/digest.py`, `backend/finn/llm/router.py`
- Test: `tests/test_api.py`, `tests/test_digest_results.py`, `tests/test_llm_router.py`

**Interfaces:**
- `GET /results/{symbol}` uses `digest._card_or_none` (rename it to the public `card_or_none`, updating the callers). A corrupt row gives 404 `{"detail": "no results on file"}`, never a 500.
- The router's `_exhausted_until` is keyed by `(provider, model)`, not provider. The error text is unchanged.
- In `attach_results`, a story gets the latest card when `-4 days ≤ story.headline.filing.filed_at − card_filed_at ≤ 45 days`, with the category and intimation rules unchanged. That is: from 4 days before the XBRL, to 45 days after.

- [ ] **Step 1: Write failing tests:**
  - `test_results_endpoint_corrupt_row_is_404`;
  - `test_quota_on_one_model_keeps_sibling_model_usable`: two Gemini models in a chain; the first returns a quota 429; the second is still called;
  - `test_same_quarter_story_45_days_later_gets_card`: a story 19 days after the card gets it;
  - `test_story_60_days_later_gets_no_card`;
  - update `test_card_not_attached_when_dates_far_apart`. Its story date 2026-12-20 is +43 days from the card (2026-11-07), which would now attach. Move the story date to 2027-01-15 (+69 days) and keep the assertion that no card is attached.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `fix: Plan 2 carry-overs (results 404 guard, per-model quota, same-quarter attach window)`.

---

