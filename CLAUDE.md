# FINN: notes for Claude Code

FINN is a mobile-first investor agent built for the ENAM Holdings AI Engineer build challenge. It has two halves:

- **Push:** a digest of NSE filings for an 18-stock portfolio, results cards with QoQ and YoY changes, and price and volume alerts.
- **Pull:** a research dossier for any NSE company, built from its earnings calls and annual report, which opens with a Promise Ledger.

Read `README.md` for the product, `docs/DESIGN.md` for the decisions, `docs/EVALS.md` for the measured results and `docs/PROJECT_BRIEF.md` for the brief.

## Deadline and submission

- **Due 15 Nov 2026.** The submission goes to assessment@enam.com with the subject "IIT Delhi – AI Engineer - 2027".
- **Deliverables:** the deployed link, this repo, the AI build history (`ai-history/`) and the covering email.
- **The email** is drafted in `docs/COVER_EMAIL.md`. The user sends it; Claude never does.

## Where it runs

- **Frontend:** https://finn-qx98.vercel.app (Next.js 16 PWA in `frontend/`).
- **API:** https://finn-peach.vercel.app (FastAPI on Vercel Python functions, in `backend/`).
- **Deploys:** both redeploy from `main` on every push.
- **Data:** the API serves a read-only SQLite snapshot, `backend/seed/finn.sqlite`.
- **Refresh:** `.github/workflows/refresh.yml` runs every 3 hours on weekdays (06:47 to 21:47 IST) and once a day at weekends, and can be run by hand with `gh workflow run refresh.yml`. It runs `scripts/refresh.py` and commits the new snapshot as github-actions[bot], only when `scripts/seed_changed.py` finds new data. Pull with `--rebase` before pushing, because the bot commits to `main`.
- **Prices:** these come from NSE's end-of-day MCP server (`finn/ingest/nse_mcp.py`), with Yahoo as the fallback for any symbol NSE can't serve. NSE's terms allow educational and research use only.

## Commands

```bash
# backend
cd backend && uv sync
uv run pytest -q                       # about 900 tests, all offline
uv run ruff check . && uv run ruff format --check .

# frontend
cd frontend && npm install
npm run test && npm run typecheck && npm run lint
npm run e2e                            # Playwright against mocked fixtures
LIVE_URL=https://finn-qx98.vercel.app LIVE_API=https://finn-peach.vercel.app \
  npx playwright test -c playwright.live.config.ts   # the deployed site
```

**Keys.** Only refreshes and live dossier builds need model keys; the tests don't.

- **Locally:** keys go in `backend/.env`, copied from `.env.example`. The two keys are `GEMINI_API_KEY` and `GROQ_API_KEY`.
- **Claude Code on the web:** set them as environment variables in the environment's settings. They are already stored as GitHub Actions secrets and in Vercel.

## How work is done here

- **Plans first.** Each change is written up as a plan in `docs/superpowers/plans/` (Plans 1 to 8 so far), then built test-first.
- **Reviews.** A final code review runs before merging to `main`.
- **History.** After a plan merges, its task ledger and reviews are archived to `ai-history/planN-*/`.
- **Feature branches.** Work happens on a feature branch, which merges into `main` once its tests pass. Pushing to `main` deploys the site.
- **Arithmetic stays in Python.** Models never compute QoQ, YoY, margins or ratios. Results come from NSE's XBRL, not from a model reading PDFs.
- **Verdict guards only downgrade.** A promise is marked kept or missed only when a later call quotes evidence for it. The guards can turn a verdict into "pending", never the other way round.
- **Model choice.** Each call goes to the cheapest model that can do the job, and every call is cached and logged with its cost.

## Rules that protect the user (public repo)

The repo and its history are public, and graders read both.

- **No secrets anywhere.** Never read, print or commit `backend/.env`. Never paste a key into a command, because command text ends up in the transcript.
- **No personal details.** Never commit the user's email address, student entry number or phone number. The placeholders in `docs/COVER_EMAIL.md` are filled in the user's mail client, never in this repo.
- **No briefing PDFs.** The challenge PDFs stay outside the repo, because the job description carries the student ID. `.gitignore` excludes `*.pdf`.
- **AI history is redacted.** Session transcripts are exported with `backend/scripts/export_history.py`, which redacts emails, entry numbers, home paths and anything shaped like a key. The user reads each export before it is published here.
- **Ask first** before anything that publishes or is hard to undo, such as rewriting history, force-pushing or making a repo public.

## Status (14 Nov 2026)

- **Plans 1 to 7 are merged and deployed:**
  - the push backend;
  - enrichment;
  - research dossiers with the Promise Ledger;
  - the frontend;
  - deployment;
  - "one loop" (promises shown on results cards);
  - NSE prices;
  - the final audit (Plan 8): bug fixes, the quiet-day view and Listen.
- **Tests:** 911 backend, 216 frontend unit and 39 end-to-end, all passing. The live Playwright checks pass.
- **Data:** all 18 holdings have dossiers (23 dossiers in total). A second hand audit found 0 wrong verdicts among the 23 resolved ones.
- **Known gaps:**
  - The NSE client takes the last SSE `data:` line without matching the request id.
  - A live dossier build is cached only on the server instance that built it.

**Left to do before 15 Nov:**
1. The user tests the app on their phone.
2. Export the final session history and publish it after the user has read it.
3. The user fills in the email's placeholders and sends it.
