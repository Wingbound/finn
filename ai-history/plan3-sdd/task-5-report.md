# Task 5 report: Promise Ledger

Commit 63c9c8f on feat/pull-research.

## Implemented
- backend/finn/models.py: Status, Actual, LedgerRow, Ledger.
- backend/finn/research/ledger.py: parse_horizon, compute_status, build_ledger.
  - Computed path: growth (YoY, Sales/Revenue or Net Profit) and margin (Operating or Financing Profit / revenue), graded per the brief's thresholds on values rounded to 2 dp. Code-written rationale. Missing period gives ("pending", None). Missing year-ago falls through to judged.
  - Judged path: one "reason" call per earlier source that has later sources. Evidence block per later source, oldest first, headed `=== id: title ===`, built with relevant_window(..., 6000). All the per-row validation rules from the controller's rulings are applied. LLMError, malformed replies and missing judgements give pending, "Not assessed".
  - No later source: pending, "Too recent to judge", no call.
  - Rows ordered by made_in (unparseable oldest), then promise id. Counts cover all five statuses. Credibility is None if nothing resolved. Note is set when fewer than 2 transcripts.

## Tests
backend/tests/test_research_ledger.py, 42 tests. They cover the parse_horizon table, compute_status (kept/partly/missed for growth and margin, lender labels, FY, pending, None cases), and build_ledger cases a to h plus LLMError/bad-reply, unknown status and rationale truncation. Evidence quotes are real T1 sentences, and the page is corrected from a wrong hint (20 to 7).

## TDD
RED: `uv run pytest tests/test_research_ledger.py -q`
```
E   ModuleNotFoundError: No module named 'finn.research.ledger'
ERROR tests/test_research_ledger.py
1 error in 0.07s
```
Mid-way failures: a float edge (18.000000000000014 vs 18) failed growth[18-kept]. Fixed by rounding to 2 dp before grading.
GREEN: `uv run pytest -q` gave 477 passed. `ruff check .` clean, `ruff format --check .` clean.

## Files
backend/finn/models.py, backend/finn/research/ledger.py, backend/tests/test_research_ledger.py

## Self-review
- compute_status wraps an internal _grade so the rationale is code-written in one place.
- Evidence that fails to locate forces pending for any status, including dropped.
- Promises are grouped by citation.source_id. Later sources are those whose quarter key sorts after made_in.

## Concerns
- Margin rationale uses the level pattern ("EBITDA margin was 21.4% in Q2 FY27 against a target of at least 22%"), since the ruling's "percentage points" wording was ambiguous.
- Only sources of kind "transcript" count as later. Annual reports are ignored for evidence.

## Fix round 1
Changes (ledger.py):
1. parse_horizon resolves only on a full-string match, after one optional leading "in"/"for"/"during". It accepts explicit quarter labels, explicit FY labels (incl. "fiscal year 2027") and the listed relative phrases. "H2 FY27", "exit FY27", "FY27-28", "end of this year" and similar give None. Bare "FY" no longer resolves.
2. target_low <= 0 gives None from _grade, so the promise is judged.
3. Period column present but the needed row labels absent gives None (judged). Pending is returned only when the column itself is absent.
4. Group "later" key is the source's quarter, falling back to made_in.
5. Row ordering sorts ids by source, then numeric suffix.
Tests added: horizon cases, lo=-5 judged (one call), missing labels, made_in vs source quarter mismatch, T1-2 before T1-10.
Command: `uv run pytest -q tests/test_research_ledger.py` -> `57 passed in 0.13s`
Full: `uv run pytest -q` -> `492 passed in 2.46s`; ruff check and format --check clean.
