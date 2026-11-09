# FINN Plan 5: Deploy, Refresh, Submission Package

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The deliverables for 15 Nov 2026:
- a phone-friendly link (frontend and API on Vercel);
- a public GitHub repo;
- a daily snapshot refresh;
- the AI build history, redacted and reviewed by the user;
- a covering-email draft the user sends.

**Architecture:** Two Vercel projects deploy from the same GitHub repo:
- `backend/` is FastAPI on Vercel's zero-config Python runtime, under Fluid compute;
- `frontend/` is Next.js.

The API serves the committed SQLite snapshot from a per-instance copy in `/tmp`. The copy is made lazily, because the code must not rely on ASGI lifespan running. Live research builds are written to that instance copy and last until the instance is recycled; the demo set lives in the snapshot.

A GitHub Actions cron runs `scripts/refresh.py` and commits the new snapshot, and Vercel redeploys on push.

**Tech Stack:** Vercel (Hobby: Fluid compute, 300 s max duration), GitHub Actions with `astral-sh/setup-uv`, uv, and the existing FastAPI and Next.js apps.

**Spec:** `docs/DESIGN.md` "Hosting (2026-11-09)", "Robustness" and §8 "Verification"; `docs/PROJECT_BRIEF.md` §9 "Submission checklist".

**Facts checked 2026-11-10:**
- Vercel's FastAPI preset finds an `app` in `main.py`, `app.py` or `index.py` and reads dependencies from `pyproject.toml` (vercel.com/kb/guide/ship-a-fastapi-app-on-vercel).
- Importing `finn.api.main` today takes 1.5 s warm and pulls in pandas and yfinance. The prices module imports them at the top, though only the refresh job uses them.

## Global Constraints

- **Secrets.** No secret enters the repo, git history, chat or a `!` command. Keys live only in Vercel env vars, GitHub Actions secrets and `backend/.env`, which stays untracked and is never read by Claude.
- **Asking first.** Ask the user before any outward-facing step: the first push, making the repo public, the first deploy, and sending anything.
- **Student ID and email.** They never appear in the repo. The AI history is redacted, and the user reviews it before it is committed.
- **Commits.** Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Checks.** `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .` and `cd frontend && npx vitest run && npx playwright test && npx eslint . && npx tsc --noEmit` stay green.

## Review Focus

1. **Cold start on Vercel.** The first request reaches an instance with an empty `/tmp`. It must copy the seed and answer the request with full data. It must not answer with an empty store or a 500. (Task 1)
2. **Two requests on a cold instance at once.** The seed copy must not race. One copy, then both requests read it. (Task 1)
3. **Refresh where NSE blocks GitHub's IPs or a key is missing.** The workflow must not commit a broken or empty snapshot. A run that fetched nothing exits 2 and commits nothing. (Task 3)
4. **CORS.** The deployed API answers the frontend origin, plus localhost in dev, but not `*`. A misconfigured `ALLOWED_ORIGINS` value fails loudly in `/health`, not silently in the browser. (Task 1)
5. **Live build on Vercel.** SSE streams through, or arrives buffered, within the 300 s limit. The stream's own 285 s cut-off fires first. (Task 2, live check)

---

### Task 1: Serverless-ready backend

**Files:**
- `backend/index.py` (new);
- `backend/finn/api/deps.py`, `backend/finn/config.py`;
- `backend/finn/ingest/prices.py`;
- `backend/scripts/refresh.py`;
- `backend/.vercelignore` (new);
- tests in `backend/tests/test_api_*.py`, `test_config.py`, `test_refresh.py`.

**Interfaces:**
- `index.py`: `from finn.api.main import app`. This is the entrypoint Vercel discovers.
- `deps.ensure_seeded(settings) -> None`: runs `copy_seed_if_empty` once per process behind a `threading.Lock`. `get_conn` calls it before connecting. The lifespan keeps calling it too, so it is harmless.
- `Settings` changes:
  - `gemini_api_key` and `groq_api_key` become `SecretStr`. Every use calls `.get_secret_value()`.
  - `allowed_origins` also accepts a comma-separated string from the env `ALLOWED_ORIGINS`.
  - When `VERCEL` is set in the env and neither `DATA_DIR` nor `DB_PATH` is given, `data_dir` defaults to `/tmp/finn`.
- `/health` adds `"cors": settings.allowed_origins` and `"seeded": bool`.
- `prices.py` imports pandas and yfinance inside `fetch_eod` only. `completed_sessions` stays importable without them.
- `refresh.py` exit codes:
  - `0`: clean;
  - `1`: partial (some sources failed; the snapshot was written);
  - `2`: nothing ingested (no filings and no prices). The output file is left untouched.

**Tests (written first):**
- `test_get_conn_seeds_without_lifespan`: a `TestClient(app)` used *without* `with`, against an empty `DB_PATH`, gets `/portfolio` holdings and `/digest` stories from the seed.
- `test_seed_copy_runs_once_under_concurrency`: 8 threads call `ensure_seeded` on an empty path, and `shutil.copyfile` is called exactly once.
- `test_vercel_defaults_to_tmp`: with `VERCEL=1`, `db_path == Path("/tmp/finn/finn.sqlite")`; with `DB_PATH` set explicitly, `DB_PATH` wins.
- `test_allowed_origins_from_csv_env`: `ALLOWED_ORIGINS="https://a.vercel.app, http://localhost:3000"` gives a list of 2.
- `test_keys_are_secret`: `repr(Settings(gemini_api_key="x-secret"))` does not contain `x-secret`, and the provider request headers still carry it.
- `test_api_import_skips_pandas`: in a subprocess, `import finn.api.main`, then `'pandas' not in sys.modules and 'yfinance' not in sys.modules`.
- `test_refresh_exit_codes`: a fake NSE and Yahoo that both fail gives exit 2 with the `--out` file unchanged; a partial failure gives 1.

- [ ] Write the tests, then implement, then run them. Add `.vercelignore` (`tests/`, `data/`, `.venv/`, `scripts/`, `**/__pycache__`).
- [ ] Measure `import finn.api.main` again, warm, and record the before and after times in the ledger.
- [ ] Commit.

### Task 2: Publish and deploy (needs the user)

**Steps:**
- [ ] **Security pass before anything leaves the machine:**
  - `git log -p --all` scanned for key patterns (`AIza`, `gsk_`, `hf_`, `sk-`, `-----BEGIN`), the student ID pattern and the user's email;
  - `git ls-files` checked for `.env`, PDFs and `data/`.

  Record the result in the ledger.
- [ ] **Ask the user, then push.** Push `main` to the GitHub repo the user created, or create it with `gh repo create finn --public --source . --push` after they approve.
- [ ] **The user imports the repo in Vercel twice:**
  1. Root Directory `backend`, framework FastAPI. Env: `GEMINI_API_KEY`, `GROQ_API_KEY`, `ALLOWED_ORIGINS`. The user types these in the dashboard.
  2. Root Directory `frontend`, framework Next.js. Env: `NEXT_PUBLIC_API_URL` = the backend URL.

  Then set the backend's `ALLOWED_ORIGINS` to the frontend URL and redeploy.
- [ ] **Live checks.** `frontend/e2e/live.spec.ts` runs only when `LIVE_URL` is set and has no mocks. It covers:
  - each tab loads with data;
  - Dig in, then a citation sheet shows a highlighted quote;
  - `/health` reports `seeded: true` and the right `cors`;
  - the cold-start time of the first API call, which is recorded.
- [ ] **One live build of an unseen ticker** through the deployed UI, for example ASIANPAINT. Record the seconds, the calls and whether SSE streamed.

### Task 3: Daily refresh

**Files:** `.github/workflows/refresh.yml`, and `backend/tests/test_workflow.py`.

- [ ] **The workflow:**
  - **Trigger:** `on: schedule: cron "30 0 * * *"` (06:00 IST) plus `workflow_dispatch`.
  - **Job setup:** `concurrency: refresh`; `permissions: contents: write`.
  - **Steps:**
    1. checkout;
    2. setup-uv;
    3. `uv sync --frozen`;
    4. `uv run python scripts/refresh.py --days 3 --out seed/finn.sqlite`, with the env keys taken from secrets;
    5. on exit 0 or 1, prune `doc_pages` and `doc_text`, `VACUUM`, and commit `backend/seed/finn.sqlite` only if it changed;
    6. on exit 2, fail the job with no commit.
  - **Seed size guard:** fail if the file is over 20 MB.
- [ ] **Test:** `test_workflow.py` loads the YAML and asserts:
  - the cron;
  - the secrets are referenced, never inlined;
  - the commit step is conditioned on the exit code;
  - the paths exist in the repo.
- [ ] Run it once with `workflow_dispatch` after the user adds the secrets. If NSE refuses GitHub's runners, record it in the ledger and document the local fallback (`scripts/refresh.py` plus a commit) in the README.
- [ ] Commit.

### Task 4: Submission package

**Files:**
- `README.md`;
- `docs/PROJECT_BRIEF.md`;
- `backend/scripts/export_history.py` and its test;
- `ai-history/sessions/*.md` (only after the user's review);
- the email draft, kept outside the repo in the scratchpad.

- [ ] **README:**
  - what FINN is, in two sentences, with the live link and 3 screenshots;
  - how Push and Pull work;
  - the architecture diagram;
  - the model routing and cost table (from EVALS and the cost ledger);
  - eval headlines: classification 91.3%, results 68/70, citations 143/143 and the ledger hand audit;
  - what is deliberately left out;
  - how to run it locally;
  - the limits: ephemeral live builds, unpriced 3.5 Flash, run-to-run variance.
- [ ] **PROJECT_BRIEF.md:** fix line 194, the stale "Hugging Face Spaces (Docker)".
- [ ] **`export_history.py`:** renders the session `*.jsonl` files to Markdown:
  - user and assistant text, plus tool calls as one-line summaries;
  - tool outputs clipped to 400 chars;
  - redaction of the student ID (regex from the JD format), the user's email, `/home/<user>` paths and anything matching a key pattern.

  Tests cover the redaction cases and the clipping. Write the output to the scratchpad first; the user reviews it before anything is committed.
- [ ] **Email draft.** It covers what was built, decisions and trade-offs, what was left out, and what comes next, with links. Run the humanizer skill over it and give the text to the user. Claude never sends it.
- [ ] **Final pass.** Run the `security-review` skill on the branch, then the whole-branch final review (opus), then the finishing-a-development-branch skill.
