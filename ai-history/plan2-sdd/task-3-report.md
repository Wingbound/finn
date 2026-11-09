# Task 3 report: Results card math

Implemented finn/enrich/results.py (table-driven metric/margin specs per format; quarter_label, quarter_end_shift, pct_change, metrics_for, build_card) and MetricRow/MarginRow/ResultsCard in finn/models.py.
R7: non-finite facts become None in metrics_for. % and bps computed from unrounded crore values; rounding only at row build.
pct_change returns None if prev <= 0 or cur < 0 (sign flip handled via notes).

TDD: RED `uv run pytest -q tests/test_results.py` -> ModuleNotFoundError finn.enrich.results. GREEN `uv run pytest -q` -> 234 passed; ruff check and format --check clean.
Tests: 11 in tests/test_results.py (brief's cases plus nan fact, swing-to-loss).
Files: backend/finn/enrich/__init__.py, backend/finn/enrich/results.py, backend/finn/models.py, backend/tests/test_results.py.
Self-review: notes order per brief; missing-comparison label derived from quarter_end_shift.
Concerns: sign-change note only when PAT is strictly <0 / >0 on both sides; zero PAT gives no note. Prev/year_ago period_end is not validated against the expected shift (Task 4 caller's job).
