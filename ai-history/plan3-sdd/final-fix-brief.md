# Plan 3 final-review fix wave: findings and controller rulings

The final review (opus, 49477a8..4f5e3e7) returned "With fixes". It probed offline (`scratchpad/probe1-4.py`) and found confidently wrong computed grades and several guard holes. Fix everything below in ONE wave. File:line references are the reviewer's, at 4f5e3e7. Every item needs tests.

## C1 (Critical): gate the computed path deterministically (`finn/research/ledger.py` `_grade`)

A computed grade is shown as the authoritative one, so it must never be computed when any of the following holds. In each case `_grade` returns None and the promise is judged.

1. The target period does not end after the call. Require `period_key > _qkey(p.made_in)`, using the same key convention as `_not_yet_due`, where FYyy becomes (yy, 4). Same-quarter or past horizons never compute.
2. The call is in Q4 and the horizon is a relative year phrase ("this year", "current year", "this fiscal", "this financial year", "next year", "next fiscal", "next financial year"). These are ambiguous in Q4 calls.
3. The horizon label or phrase does not appear in the normalised quote. The horizon is LLM text and must be grounded. Compare normalised forms, allowing "FY27", "FY 27" and "FY2027" to match each other, and "Q3 FY27" to match "Q3FY27".
4. The quote lacks the metric's words:
   - revenue_growth needs revenue, sales, top line, topline or turnover;
   - pat_growth needs PAT, net profit or profit after tax;
   - ebitda_margin needs EBITDA, operating margin or OPM.

   All are whole words, case-insensitive.
5. The quote contains a metric-mismatch cue (word-boundaried, case-insensitive):
   - `ebit` (not ebitda);
   - qoq, quarter-on-quarter, quarter on quarter, sequential*;
   - cqgr;
   - constant currency;
   - dollar*, usd, us$, $;
   - bps, basis points;
   - expan*, improv*;
   - `by \d` (a margin-change target).
6. The company is a lender (`financials.is_lender(annual)`) and the metric is ebitda_margin.
7. The P&L's fiscal year-end month (the last annual column, excluding TTM) is not "Mar". Skip the computed path entirely.

Also fix the computed rationale for ranges. When `target_high` is set, say "against a target of 15–18%". Otherwise say "at least 15%".

Add one test per gate, using synthetic promises and tables. Existing computed tests must still compute: adjust their quotes to contain the metric word and horizon label, without weakening the assertions.

## C2 (Critical): negative net worth (`finn/research/financials.py`)

- When Equity Capital + Reserves ≤ 0: `debt_to_equity = None`, no debt-free flag, and add the flag `Flag("concern", f"Net worth is negative (₹{nw:,.0f} cr): debt exceeds the equity base")`.
- Test: net worth −4,900 with debt 20,000 gives that concern, D/E None, and no "debt-free" flag.
- Also (a Task 2 minor): the FCF flag text renders a negative as "negative over 3 years (−₹30 cr)", with the sign before the ₹. Do not print "₹-30".

## I1: the judge rationale must be grounded (`ledger.py`)

- **kept / partly / missed:** keep the LLM rationale only if `numbers_grounded(rationale, promise.quote + "\n" + evidence.quote)` holds and it is ≤ 30 words. Otherwise use "See the later evidence quote."
- **pending:** a code string only.
  - "Too recent to judge" when there is no later source;
  - "Target not yet due — tracking is not delivery" for the downgrade;
  - "No verifiable later evidence" when evidence failed;
  - "No later evidence of the outcome yet" otherwise.
- **dropped:** "Not mentioned in the later calls".
- Tests: a kept rationale with an ungrounded number becomes the template; a pending row's LLM rationale is replaced.

## I2: LLM failures must be visible and must not overwrite good dossiers

- **Reporting failures:**
  - `extract_promises` must report an `LLMError` or invalid reply shape to its caller. Add an optional `notes: list[str] | None`, or return the failure through the guard dict.
  - `build_dossier` records "Guidance from {title} could not be read (model unavailable)".
  - Do the same for snapshot and bull/bear ("Snapshot unavailable (model unavailable)") and for ledger judge groups ("Some promises could not be judged (model unavailable)").
- **Empty ledger:** when ≥ 2 transcripts were read but the ledger has 0 rows, set `ledger.note = f"No verifiable forward-looking guidance found in {n} calls"`, unless a model-unavailable note already explains it.
- **Plain-English failure notes:** "Ledger could not be built (internal error)" in place of "ledger failed: KeyError". Keep the exception type in a log line only.
- **Never overwrite good with degraded:** a dossier is degraded when any note says "model unavailable", "could not be built" or "skipped: build deadline reached".
  - API `/build`: if the new dossier is degraded and a stored dossier exists, do NOT save it. Stream `done` with the stored dossier, plus a progress message "Live rebuild was incomplete; showing the last complete dossier".
  - The CLI does the same: it does not overwrite, and prints a warning.
- **Tests:** a pipeline test with a router raising `LLMError` everywhere gives notes present, the ledger note set, and nothing raising. An API test: a degraded rebuild does not overwrite the stored dossier.

## I3: stay inside Vercel's 300 s limit

- `collect_sources(..., deadline: float | None = None, now=time.monotonic)` stops fetching further sources once past the deadline, noting "Remaining sources skipped: build deadline reached".
- `build_dossier`: start no new LLM call or stage when less than 60 s of `deadline_s` remain, with the same note style. `build_ledger` accepts a `should_stop: Callable[[], bool]` that is checked before each judge group.
- **SSE `gen()`:**
  - wait with `q.get(timeout=15)`, and on timeout yield a comment line `: ping\n\n`;
  - if 285 s have passed since the stream started, yield `event: error` with `{"detail": "build timed out"}` and stop.
- **Tests:** past-deadline source skipping; `should_stop` stops judge calls; a generator ping and timeout test with a patched clock and queue (unit-test the generator helper).

## I4: conditionals and past facts (`guidance.py`, plus the prompt)

- The system prompt adds: "Exclude conditional or hypothetical statements (if, unless, assuming, provided, subject to)."
- **Conditional rejection:** reject a promise whose normalised quote, or the earlier part of its sentence (the same sentence-prefix logic `cite.locate` uses), contains whole-word if, unless, assuming, provided or "subject to".
- **Forward-only cues:** replace the prefix cues with whole-word forms:
  - expect, expects, expecting;
  - will; shall; would;
  - plan to, plans to, planning;
  - aim to, aims to, aiming;
  - target, targets, targeting;
  - guide, guidance, guiding;
  - intend, intends, intending;
  - anticipate, anticipates, anticipating;
  - aspire, aspires, aspiration;
  - commit, committed to, commits;
  - outlook, going forward, on track, upcoming, should, likely, confident;
  - look to, looking to, look forward;
  - "by FY" (as a whole phrase), "next".

  Drop the past forms (expected, planned, targeted, aimed) and the prefix matches ("plant", "willing").
- **Tests:**
  - "If demand recovers, we will grow revenue by 15% in FY27" is dropped;
  - "Assuming …, we expect …" is dropped;
  - a fragment cut after "Unless the macro deteriorates further," is dropped;
  - "Our plant utilization was 80%" is dropped;
  - "As expected, revenue grew 12%" is dropped;
  - "We are willing to look at" is dropped unless it has another cue (expect "look to" to be a cue, so pick an example without one);
  - "We expect revenue to grow 15% in FY27" is kept.

## I5: the judged path's period handling

- Each promise line in the judge prompt includes `made_in` and the resolved period when there is one, for example `(made in Q2 FY27; target period FY27)`.
- **Lenient period scan for the not-yet-due downgrade only:** scan the horizon plus the quote for the first period mention:
  - FY labels (FY27, FY 27, FY2027, fiscal 2027);
  - quarter labels;
  - "march 2027" / "mar 2027", meaning FY27 Q4;
  - "end of this year", "this financial year", "this fiscal", "current year", resolved from `made_in` (in a Q4 call, "this year" means the next FY).
- **Long horizon becomes relative:** "long" is FY ≥ newest FY + 2, replacing the fixed FY28–FY32 and 2028–2032. Keep the word cues (long-term, medium-term, aspiration, over the next few years).
- **Tests:** "by FY27", "end of FY27", "exit FY27", "by March 2027" and "by the end of this financial year" in a Q2 FY27 context all downgrade kept to pending. An FY29 target with newest FY27 is long.

## I6: page citations ground numbers in their quote only (`synthesis.py`)

- For transcript or AR citations, use `numbers_grounded(text, quote)`.
- FACTS-cited points ground in the FACTS line, as now.
- Test: a T1-cited point carrying a FACTS-only number is dropped.

## I7: credibility on small samples

- `credibility_pct = None` when fewer than 3 rows are resolved (kept + partly + missed).
- The FACTS ledger line includes "{r} of {n} promises resolved", and shows credibility only when it is not None.
- Test.

## I8: SSE worker ordering and live-build excerpts (`api/main.py`)

- **Order of operations:**
  1. Put `done` on the queue first.
  2. Then try to save, logging a failure without changing the stream.
  3. Put `_DONE` in a nested `finally`, so `conn.close()` raising cannot block it.
- **Excerpts:** the `done` payload adds `excerpts: {source_id: {page: text}}` for every cited page (ledger promise and evidence citations, snapshot, bull and bear), excluding FACTS. The client then needs no second request for a live-built dossier.
- **Tests:** a save failure still gives `done`; excerpts are present for the cited pages.

## Minors, fixed in this wave

- **Lender FACTS label:** the lender FACTS line says "Financing margin change", not "Operating margin change".
- **`fetch_company` data check:** use `any(t.values())` for "has data", so a table with headers and no rows doesn't count.
- **Judge prompt:** add "missed only if management cut, lowered or moved the target, or the stated time passed without it".
- **"dropped" with truncated sources:** not allowed when any later source was truncated by the evidence budget; it becomes pending. Tell the judge in the prompt when a call is truncated.
- **Eval table:** add a FACTS-citations column (`r.facts`).
- **Ledger note when sources are absent:** "Not enough concall transcripts on file (found 0)" when screener lists concalls but none were readable. Keep it as is; it fails safe.

## Docs (graded deliverables)

**DESIGN.md:**
- :81: transcripts are read whole, not "chunked by section".
- :82: the ledger runs on Gemini Flash-Lite with evidence gating, not "Pro-class".
- :86: dossiers are cached per ticker, and a rebuild is allowed after 10 minutes, unless it is degraded.
- :107 and :110: the API is read-only except `/research/search` and `/research/{sym}/build`.
- :94:
  - the LLM budget is about 9 calls by design (4 extraction, ≤ 3 judge, 2 synthesis), not an enforced cap of 12;
  - the deadline is checked between stages and within sources and judge groups, with a 60 s margin;
  - the SSE times out at 285 s.
- :95: state the grading rules exactly:
  - growth ≥ lo is kept, ≥ 0.8·lo is partly;
  - margin ≥ lo is kept, ≥ lo − 1 pp is partly;
  - computed only under the C1 gates;
  - lo ≤ 0, segment, lender-margin and non-March cases are judged;
  - not-yet-due and long-horizon kept become pending;
  - "dropped" needs ≥ 2 later calls with no truncation;
  - T1 promises are always pending;
  - credibility = (kept + 0.5·partly)/(kept + partly + missed), shown only with ≥ 3 resolved.

**PROJECT_BRIEF.md:** :191 "stronger Gemini model" and :204 `scripts/seed.py` must reflect the current code (Flash-Lite routing; `scripts/refresh.py` and `scripts/research.py`).

**EVALS.md §4:**
- state that citation verification is 100% *by construction*, because the eval re-runs the same matcher;
- add that a hand audit of resolved rows is the real fairness measure, with the results pending (controller);
- explain that the drop rate includes the cue filter, de-duplication and the 8-item cap.

Leave "Live results: pending (controller)".

## Out of scope (stays deferred)

Everything the reviewer triaged STAY-DEFERRED, plus:
- repeated promises counting more than once;
- concurrency cap and in-flight de-duplication;
- list routes loading whole dossiers;
- the global stats delta;
- the progress() placement;
- the 40 MB streaming cap.

## Process

- TDD.
- `cd backend && uv run pytest -q` (full), `uv run ruff check .` and `uv run ruff format --check .`.
- Logical commits (C1, C2, I1–I2, I3, I4–I5, I6–I8, minors, docs), each message ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No network and no live builds. Never read `backend/.env`.
- Report to `/home/snig/Desktop/Sem 9/Placement CV/ENAM/finn/.superpowers/sdd/2026-11-09-plan3-pull-research/final-fix-report.md`, per item, with the covering tests, commands and pasted output lines.
