# Task 1 report
Implemented pyproject (uv_build, module-root="" so package is backend/finn/), Settings/get_settings, Holding/load_portfolio, portfolio.yaml (18 holdings), .env.example, tests/test_portfolio.py.
RED: `uv run pytest tests/test_portfolio.py` -> ModuleNotFoundError: No module named 'finn.portfolio' (expected, not yet written).
GREEN: `uv run pytest` -> 3 passed. `uv run ruff check .` clean.
Notes: Settings.db_path is Path|None defaulting via validator to data_dir/"finn.sqlite". uv.lock committed; .env not committed (gitignored).
