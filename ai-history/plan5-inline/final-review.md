# Plan 5 final review (whole branch b937d7f..fc399f3, security focus)

Reviewer: final whole-branch reviewer, one pass over the review package, then reads of the touched modules (`finn/api/main.py`, `deps.py`, `seed.py`, `config.py`, `llm/router.py`, `llm/providers.py`, `ingest/screener.py`, `scripts/refresh.py`, `scripts/compact_seed.py`, `scripts/export_history.py`, the workflow, the frontend build trigger).

Checks run:
- `cd backend && uv run pytest -q`: 778 passed. `ruff check`: clean. `ruff format --check`: clean.
- `cd frontend && npx vitest run`: 132 passed. `tsc --noEmit` and `eslint .`: clean. (Playwright was not re-run.)
- Read-only GETs to the deployed API: `/health`, `/research`, `/docs`, `/openapi.json`, a 404 dossier lookup, one search, and CORS preflights. No builds were triggered.
- Local probes: SecretStr truthiness, ALLOWED_ORIGINS misconfigurations against `CORSMiddleware`, a truncated store passed to `copy_seed_if_empty`, an injected crash in `refresh.main`, compaction of an unchanged seed, and about 45 redaction inputs against `export_history.redact`.
- I rendered the real main-session transcript (41 MB) and the 96 subagent transcripts with the shipped exporter, then scanned the output with broader patterns. The scan printed only masked shapes and counts, never a value. The git author email was read in-process and never printed.

## Strengths

- **The cold-start design is right.** `ensure_seeded` sits in `get_conn`, so it never depends on the lifespan. It takes a per-path lock with a set fast-path. Two tests cover it, both meaningful: `TestClient` without `with`, and 8 threads with a slowed `copyfile`. Live `/health` reports `seeded: true`.
- **Refresh works on a copy.** `refresh.py` runs on a `backup()` copy and swaps it in with an atomic `replace`. An exit-2 run provably leaves the target byte-identical and leaves no temp files behind (test plus my probe). Killing the job mid-run cannot half-write `seed/finn.sqlite`.
- **Secrets are handled cleanly.** `SecretStr` with a single `api_key()` accessor. Gemini's key goes in the `x-goog-api-key` header, not the query string, so httpx error strings cannot carry it. Neither `repr` nor `model_dump` shows the key. `.gitignore` and `.vercelignore` both exclude `.env` and `.env.*`, and only `.env.example` is tracked.
- **No script-injection surface in the workflow.** The only `${{ }}` in a `run:` line is the step's own numeric `$?`. There are no `github.event.*` inputs, the secrets are step-scoped, and only `seed/finn.sqlite` is ever `git add`ed.
- **The heavy dependencies are out of the API.** Moving pandas and yfinance into a dependency group is a real improvement: the bundle and the cold-import time both shrank. The subprocess test guards the import.
- **The repo scan is clean.** No key pattern, no student-ID shape and no git-author email appears in tracked files outside the exporter's own fake test fixtures.

## Review Focus, item by item

1. **Cold start: holds.** The lazy seed on the first request is verified by test and by live `/health`. The remaining edge case (a half-written copy is never retried) is Minor 1.
2. **Concurrent cold requests: holds.** One copy runs under the lock. The test asserts a single `copyfile` across 8 threads.
3. **Refresh with NSE blocked or a key missing: holds for the literal requirement, with gaps.** Nothing-ingested exits 2: the step fails and nothing is committed. But a crash or an unexpected exit code is reported as a partial success and does produce a commit (Important 2). A missing key gives a silent exit 0 (Minor 3).
4. **CORS: partly met.** The deployed API allows only the frontend, and a foreign preflight gets a 400 (verified live). But the plan asked that a misconfigured value "fail loudly in /health". The implementation only echoes the list, so `/health` says `ok: true` when the browser is being blocked (Minor 2).
5. **Live build and SSE: accepted on the ledger's evidence.** The guard is 285 s against Vercel's 300 s, and three live builds ran 75 to 83 s. The 300 s limit is assumed, not pinned in the repo (Minor 8).

## Issues

### Critical

None.

### Important

#### I1. `/research/{sym}/build` lets any anonymous caller spend the LLM keys, with no cap

- **Where:** `backend/finn/api/main.py:362-382`, `frontend/src/components/research/SearchBox.tsx:64`.
- **What's wrong:**
  - The endpoint is an unauthenticated GET.
  - It has no global or per-client limit, and no dedupe of in-flight builds of the same symbol.
  - The symbol is never validated.
  - CORS does not protect it: curl ignores CORS.
  - The API's Swagger UI is public (`/docs` answers 200), so anyone can click "Try it out".
  - The frontend's search links to `/research/X?build=1`, which starts a build on page load, so every such link spends money when opened.
- **Failing scenario:** a loop over 30 to 100 NSE symbols, one GET each, costs about 9 model calls per build.
  - On free-tier keys, that exhausts Gemini's daily request quota in minutes. The assessor's "Build" then fails for the rest of the day. If GitHub's secrets share the keys, the 06:00 refresh loses its LLM classification too.
  - If billing is enabled on the Gemini project, it is real spend: about $0.03 to $0.07 per build at list price, unbounded. Treat this one as Critical in that case.
- **Second scenario, the symbol:** paths are percent-decoded before routing.
  - `GET /research/TCS%3Fx%3D1` yields `symbol = "TCS?X=1"`. Confirmed live: the 404 echoes `"/research/TCS?X=1/build"`.
  - `fetch_company` then requests `https://www.screener.in/company/TCS?X=1/consolidated/`, and screener serves the TCS page.
  - Each `?X=n` variant is a fresh, uncached build of the same company, stored under a junk symbol in that instance's `/research` list.
- **Fix (cheap, per instance; enough for a demo):**
  - Validate the symbol with `^[A-Z0-9&-]{1,20}$` in `research_build`, `research_get` and `research_source_page`.
  - Wrap `_build_worker` in a `threading.BoundedSemaphore(2)`. When it is full, answer with an SSE `error` ("busy, try again shortly").
  - Keep a module-level `{symbol: queue}` of in-flight builds, so a second request for the same symbol attaches to the running build instead of starting another.
  - Add a process-wide cap such as 20 builds per rolling hour.
  - Set `docs_url=None, redoc_url=None, openapi_url=None` when `VERCEL` is set.
  - Optionally add a Vercel firewall rate-limit rule on `/research/*/build`, and a `robots.txt` that disallows `/research/*?build=1` on the frontend.

#### I2. A crashed refresh is reported as "partial" and commits a recompacted, unchanged snapshot

- **Where:** `backend/scripts/refresh.py:209` (uncaught exceptions exit 1), `.github/workflows/refresh.yml:41-52`.
- **What's wrong:**
  - Exit 1 means "partial" in the contract, but it is also Python's exit status for any uncaught exception. Most of `refresh()` is unguarded: `classify_pending` (line 113), `db.upsert_prices`, `load_portfolio`, `src.backup` (line 173).
  - The workflow maps every code except 2 to `exit 0`, including 137 (OOM) and 143 (SIGTERM).
- **Verified failing scenario:**
  - I injected a `RuntimeError` into `refresh` and ran `main --out <copy of seed>`. It exited 1, left the target unchanged, and left `finn.sqlite.refresh-tmp` behind.
  - In the workflow, that run prints `::warning::Partial refresh` and the Compact step runs.
  - Compacting an unchanged seed changes its bytes: header change counter, byte 28, verified with `cmp`. So `git diff --quiet` sees a change, and the job commits "Refresh snapshot (exit 1)" with yesterday's data, pushes, redeploys Vercel (wiping live builds), and goes green.
  - A refresh that crashes every day therefore looks like a daily partial success. Only `filings_as_of` drifting in the app would show it.
- **Fix:**
  - Make the codes distinct from Python's: wrap the body of `main` in `try/except Exception`, log the error, and `return 4` after `_discard(work)`.
  - Optionally move "partial" to 3.
  - In the workflow, use `case "$code" in 0|1) ;; 2) echo ::error::...; exit 1;; *) echo "::error::refresh crashed ($code)"; exit 1;; esac`.
  - Add a `test_refresh_crash_is_not_partial`.

#### I3. The exporter's redaction misses realistic forms of the very identifiers it targets

- **Where:** `backend/scripts/export_history.py:33-49`, `:112`, `:129`, `:140`.
- **Today's transcripts are clean.** My masked scan of the real main session and all 96 subagent transcripts found no surviving entry-number, Kerberos, partial-email, key or git-author-email shapes. The gaps are latent, but the tool is the last automated line before a public publish, and each fix is small.
- **Probed failures:**
  - **Clipping runs before redaction.** `redact` runs once, on the joined output (line 140), after tool results were clipped to 400 chars (line 129) and compaction summaries to 1,200 (line 112). An identifier straddling the cut no longer matches, and its head survives:
    - `someone.private@gmai… [14 more characters]`: the whole email local part leaks;
    - `JD_2022ME1123…`;
    - `IzaSyA1234567890ab…`.
  - **Word boundaries fail next to `_`.** `JD_2022ME11234.pdf`, `2022ME11234_resume`, `user_me1220123_x` and `id:me1220123abc` all survive. Underscored file names are the likeliest place an entry number appears; the DESIGN doc notes that the JD carries it.
  - **Case.** `ME1220123` and `Me1220123` (uppercase or mixed Kerberos) and `2022me11234` (lowercase entry number) all survive, because the Kerberos rule is `[a-z]` only and the entry rule is `[A-Z]` only.
  - **Escaped and obfuscated emails.**
    - `someone\.private@gmail\.com`, the exact form a leak-scan grep uses, survives whole.
    - The Grep tool's `pattern` is rendered verbatim by `_tool_line`, so a Grep for the email would publish it.
    - `%40`, `(at)`, `[at] ... [dot]` and `local@\ngmail.com` also survive.
  - **Paths.** `C:\Users\<Name>\...` (Windows backslashes) survives. The dashed Claude-project form `-home-<user>-Desktop-...` survives 72 times in the main session's output and 20 times in the subagents' (the scratchpad and project paths).
  - **Keys.** These survive:
    - `sk-proj-…`, `sk-ant-api03-…` and `github_pat_…`;
    - any key wrapped across lines;
    - `GEMINI_API_KEY=<value>` assignments where the value has no known prefix.
- **Fix:**
  1. Redact each block's raw text before clipping, and keep the final pass.
  2. Replace `\b` with `(?<![A-Za-z0-9])` and `(?![0-9])`, and compile the ID rules with `re.I`.
  3. Accept literal strings from an untracked file, for example `--redact-file ~/.config/finn-redact.txt` holding the email, entry number, Kerberos ID, username and phone. Replace each case-insensitively, also in its regex-escaped (`re.escape`), `%40` and dashed forms. That is the only robust guard for the known values. The docstring's "without needing to know whose history it is" is the design choice behind most of these misses.
  4. Add rules for `[A-Za-z]:\\Users\\[^\\\s]+`, `-home-[A-Za-z0-9._]+-`, `(?:sk-(?:proj|ant)-|github_pat_)[\w-]{20,}` and `(?i)(?:api_?key|token|secret)\s*[=:]\s*\S{12,}`.
  5. Add tests for each probe above.

### Minor

#### M1. The seed copy is not atomic, and a half-copied store is never retried

- **Where:** `backend/finn/api/seed.py:45`, `backend/finn/api/deps.py:30-32`.
- **Scenario:** `copyfile` fails partway (ENOSPC, or an exception mid-write). The next request finds a malformed file. `_has_filings` raises `DatabaseError`, so the function returns False ("never overwritten"), and `_seeded` marks the path as done. I verified this with truncations at 10, 50 and 90%: none were recopied. Every request on that instance then 500s until it recycles.
- **Fix:** copy to `db_path.with_name(db_path.name + ".seeding")`, then `os.replace` it onto `db_path`.

#### M2. `/health` echoes ALLOWED_ORIGINS but does not flag a bad value; on Vercel, the default is `*`

- **Where:** `backend/finn/config.py:34-46`, `backend/finn/api/main.py:111`.
- **What I verified:** these values each leave `/health` at `ok: true` while the browser gets no `Access-Control-Allow-Origin` header:
  - `https://finn-qx98.vercel.app/` (a trailing slash);
  - `finn-qx98.vercel.app` (no scheme);
  - an empty value.
- **Second problem:** with `ALLOWED_ORIGINS` unset, a Vercel deployment allows `*`, which the plan rules out.
- **Fix:** strip trailing `/`, and reject entries that lack a scheme or carry a path. Under `VERCEL`, treat `*` or an empty list as misconfigured, and report `"ok": false, "cors_error": "..."`.

#### M3. A missing LLM key in CI exits 0 with no warning

- **Where:** `backend/scripts/refresh.py:40-43`.
- **Scenario:** a secret is deleted or renamed. Every run then commits rules-only classifications with no enrichment, and the job shows a green "exit 0".
- **Fix:** when `use_llm` is set and no key exists, append to `errors` (exit 1, with the workflow's warning). Or add a workflow step that fails when both secrets are empty.

#### M4. Refresh temp files are not ignored, and a refresh into the live store loses concurrent writes

- **Where:** `backend/scripts/refresh.py:167,188-190`, `.gitignore`.
- **What's wrong:** `seed/finn.sqlite.refresh-tmp` and its `-wal` and `-shm` sidecars match no ignore rule, and `!backend/seed/*.sqlite` would un-ignore a `.sqlite` name there.
  - After a crashed local run (see I2), `git add backend/seed` or `git add -A` commits the full, uncompacted store.
  - Without `--out`, the target is the serving `DB_PATH`. A dossier the local server saves between `backup()` and `replace()` is lost, and the `-wal` is unlinked under a live connection.
- **Fix:**
  - Add `backend/seed/*.refresh-tmp*` to `.gitignore`.
  - Document `--out` as a must when a server is running, or refuse to run without `--out` when the target has a live `-wal`.

#### M5. Workflow hardening

- **Where:** `.github/workflows/refresh.yml:26-28,67`.
- **What's wrong:**
  - `actions/checkout` persists the `contents: write` token in `.git/config` for every later step, including `uv sync`, yfinance and pypdf parsing NSE PDFs.
  - The actions are pinned to tags, not SHAs.
  - `git push` fails outright if `main` moved during the run.
- **Fix:**
  - Set `persist-credentials: false`, and push with an explicit token in the last step only.
  - Pin `setup-uv` and `checkout` to commit SHAs, with the tag in a comment.
  - Run `git pull --rebase` before the push.

#### M6. The README's local fallback skips compaction

- **Where:** `README.md` ("To refresh the data…") and Known limits.
- **What's wrong:** the hand-commit fallback runs `refresh.py --out seed/finn.sqlite` without `scripts/compact_seed.py`. The committed seed then keeps `doc_pages` and `doc_text`, and no size check runs.
- **Fix:** add `uv run python scripts/compact_seed.py seed/finn.sqlite --max-mb 20` to both places.

#### M7. Leftover `getattr` on a key field

- **Where:** `backend/finn/llm/router.py:125`.
- **What's wrong:** `keyed = [... if getattr(self.settings, PROVIDERS[p][2])]` still reads the `SecretStr` object. It works only because `SecretStr` defines `__len__` (I verified `bool(SecretStr("")) is False`).
- **Fix:** use `self.settings.api_key(...)`, for one code path and no reliance on that dunder.

#### M8. The 285 s guard assumes a 300 s limit the repo does not pin

- **Where:** `backend/finn/api/main.py:281`. There is no `backend/vercel.json`.
- **Fix:** add `{"functions": {"index.py": {"maxDuration": 300}}}`, so the project's dashboard default cannot silently sit below the guard.

#### M9. Live checks miss two plan items

- **Where:** `frontend/e2e-live/live.spec.ts`, `docs/EVALS.md` §5.
- **What's missing:** the plan asked the live spec to assert `/health` `seeded: true` with the right `cors`, and to record the cold-start time of the first API call. The spec has neither. EVALS gives warm latencies only. The ledger has the `/health` result from a manual check.
- **Fix:** add a `request.get(API/health)` assertion, and record one cold first-call time in EVALS.

#### M10. Exporter fidelity

- **Where:** `backend/scripts/export_history.py:92-107`.
- **What's wrong:**
  - `isSidechain` lines are dropped, so all 96 subagent transcripts render as an empty `# Session agent-…` header.
  - `<task-notification>` blocks (9 in the main session) render as `## You`, which attributes harness notifications to the user in a public file.
  - The allowlist's `endswith("users.noreply.github.com")` also keeps `x@evilusers.noreply.github.com`. That is harmless, but the check should be `endswith("@users.noreply.github.com")`.
- **Fix:**
  - Add `<task-notification>` to `_internal`.
  - Add a `--sidechains` flag, if subagent transcripts are meant to be published.
  - Anchor the suffix on `@`.

#### M11. The OS username is in a tracked doc

- **Where:** `docs/DESIGN.md:226`.
- **What's wrong:** the line contains `~/.claude/projects/-home-<user>-Desktop-…`, the dashed path form that the home-path rule and the history security pass both missed.
- **Fix:** write `~/.claude/projects/<project>/*.jsonl`.

#### M12. `/research/search` has no length cap and echoes upstream errors

- **Where:** `backend/finn/api/main.py:255`.
- **What's wrong:** `q` is unbounded (a 3,000-character query was proxied to screener live). A 502 echoes httpx's message, including the full upstream URL. Anyone can use the API to hammer screener from Vercel's egress IPs, which risks a block that would also break live builds.
- **Fix:** set `Query(min_length=1, max_length=64)`, return a generic 502 detail, and optionally add a small per-instance rate limit.

#### M13. The snapshot is committed every day, even with no new data

- **Where:** `.github/workflows/refresh.yml:57-67`.
- **What's wrong:** `prices_as_of` and VACUUM change bytes on every run. So every day brings a 3 MB binary commit and a Vercel redeploy that wipes the live builds.
- **Fix:** acceptable for the submission window. Later, skip the commit when `filings_new == 0` and no bar's date is new.

## Declined to judge

- **Whether the deployed Gemini and Groq keys have billing enabled, and whether GitHub's secrets are the same keys.** Both decide whether I1 is quota loss or real money. I cannot see the dashboards.
- **Vercel Hobby's actual configured max duration, and Fluid compute's treatment of the daemon build thread after the response ends.** These are platform behaviors. I did not trigger a build to measure them.
- **The ASIANPAINT HTTP/2 tail loss.** The executor ruled it a client artifact, on the evidence of the browser and HTTP/1.1 runs. Reproducing it would need a paid build.
- **The full Playwright suites (`npx playwright test`, the live config).** Not re-run: one needs a browser install and the other hits the deployed site. vitest, tsc and eslint passed.
- **XSS from LLM-written dossier text.** It is rendered by React, which escapes it. The frontend rendering code was outside this diff.
- **Public NSE-filing emails in the committed seed** (scrutinizer and company-secretary addresses). They are public regulatory data, not the user's.
- **The user's first name in the AI history.** The executor's ruling records it as kept by the user's choice.
- **GitHub disabling scheduled workflows after 60 days of no activity.** Irrelevant before the 15 Nov deadline, and the bot's commits count as activity.
- **`vercel deploy` from a local CLI uploading untracked local files** (scratch SQLite stores, caches). The deploy is Git-based per the ledger, so only tracked files ship.
- **POST bodies for `/digest` and `/alerts` as CPU-DoS vectors.** They are bounded by pydantic and Vercel's 4.5 MB body cap. I did not profile them.

## Verdict

**Ready to merge? With fixes.** The deployment meets Review Focus items 1, 2 and 5 and the letter of item 3. Secrets handling, the bundle and the repo are clean. But three things should be fixed before the history export and before the link goes to assessors:

- I3: fix the exporter's redaction gaps before it runs on the full transcript;
- I1: cap and dedupe the public build endpoint;
- I2: separate "crashed" from "partial" in the refresh contract.

M1, M2 and M4 are short follow-ups.
