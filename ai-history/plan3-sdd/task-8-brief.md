### Task 8: Research eval and docs

**Files:**
- Create: `backend/scripts/eval_research.py`
- Modify: `docs/EVALS.md` (§4 "Research dossiers"), `docs/DESIGN.md`
- Test: `backend/tests/test_eval_research.py`

**Interfaces:** `scripts/eval_research.py [--db PATH]`. For every stored dossier it reports:
- (a) citation verification: re-`locate` every citation in the dossier against its stored source pages. Expect 100%; anything less is a bug, so list the failures;
- (b) the ledger status distribution, and computed versus judged counts;
- (c) the guard drop rate: promises proposed versus kept. This requires `build_dossier` to record in `notes` or `cost`, as `{"promises_proposed": n, "promises_kept": k, "points_proposed": …, "points_kept": …}`. Add a `guard` dict to `Dossier`.
- (d) cost and seconds.

It prints a Markdown table and exits 0.

- [ ] **Step 1: Write failing tests:** the eval on a dossier saved by the Task 7 offline test reports 100% citation verification. A deliberately corrupted citation in a saved dossier is reported as a failure.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implement**, including the `Dossier.guard` field and its population in `build_dossier`, plus a test.
- [ ] **Step 4:** `uv run pytest -q` and ruff.
- [ ] **Step 5: Docs.**
  - `docs/EVALS.md` gets "## 4. Research dossiers": method, plus a placeholder "Live results: pending (controller)".
  - `docs/DESIGN.md`: the Pull section notes the request-time exception (search and build only), the live-build budget, and the ledger grading rules (computed thresholds; evidence-judged otherwise).
- [ ] **Step 6: Commit** `feat(research): dossier eval (citation verification, guard drop rate) and docs`.

---

## After the tasks (controller)

1. **Choose the demo set.** 3–5 companies, at least 2 outside the portfolio, each with ≥ 4 transcripts with links, at least one with numeric guidance, and ideally one with visible misses. Build them live into a scratch seed with `scripts/research.py`.
2. **Generalisation.** Build 3 random NSE tickers not in either set.
3. **Eval.** Run `scripts/eval_research.py`, then fill in EVALS §4.
4. **Seed.** Install it; the final review runs before the merge.
