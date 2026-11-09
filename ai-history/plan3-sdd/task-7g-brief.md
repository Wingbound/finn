# Task 7g (live-tuning addendum): deterministic verdict guards on judged ledger rows

## Why

The rebuild on 2026-11-09 produced 11 resolved ledger rows across 7 dossiers. A hand audit found 3 of them wrong. Each mistake is mechanical, so code can catch it after the judge replies:

1. **Restated target taken as delivery.** DIXON, a Q3 FY26 promise to start Noida mass production by Q2 FY27, was judged **kept**. The evidence quote (Q4 FY26 call) is "…is nearing completion, and we expect the operation to commence by Q2 this fiscal." That is a reaffirmation written in the future tense. The prompt already says reaffirmation is not delivery, but the model ignored it.
2. **A number below the target judged kept.** IDEA's promise was "That range of INR 50 billion to INR 60 billion, which we had indicated for H1…" (target_low=50, target_high=60, quantitative). The evidence is "For the quarter was Rs. 17.5 billion and for H1FY26 at Rs. 42 billion." The verdict was **kept**, with the rationale "met the INR 50-60 billion target range". 42 < 50.
3. **Evidence about another period.** INDIGO's horizon was "Q4 FY26" (a capacity target of about 10%). The evidence is "June quarter's capacity growth came in at 3% on a year-over-year basis…". The June quarter is Q1 FY27, not Q4 FY26, yet the row was judged **missed**.

## Change (`backend/finn/research/ledger.py` only, plus tests and the eval column)

Add three guards. They run on every judged verdict, in `_judge_group`, after `_judge_one` and before `_not_yet_due`. Each guard **only ever downgrades to `pending`** (evidence `None`), and each sets a fixed rationale. Computed rows are untouched.

### A. Other-period guard: applies to `kept`, `partly` and `missed`

- **The horizon's period** comes from `p.horizon` (normalized):
  - a quarter: `q([1-4])\s*fy\s*'?(\d{2}|\d{4})` → (q, yy);
  - otherwise a fiscal year: `(?:fy|fiscal(?: year)?)\s*'?(\d{2}|\d{4})` → yy.

  If neither is found, skip the guard.
- **Quarter mentions in the evidence quote** (normalized):
  - `q([1-4])` with an optional `\s*fy\s*'?(\d{2}|\d{4})`;
  - `(first|second|third|fourth) quarter` → 1–4;
  - `(june|september|december|march) quarter` → 1, 2, 3, 4 (Indian fiscal: Apr–Jun is Q1).

  A mention without an FY matches any FY.
- **FY mentions in the evidence:** the same FY pattern as the horizon. Do not count an FY that is part of a quarter mention: strip the quarter mentions first.
- **Horizon is a quarter:** if the evidence has at least one quarter mention and none of them equals (q, yy) (or q alone, for mentions without an FY), downgrade.
- **Horizon is an FY:** if the evidence has at least one FY mention and none of them equals yy, downgrade. Quarter-only evidence passes.
- Rationale: `"The later quote is about a different period"`.

### B. Restated-target guard: applies to `kept` and `partly`

- Downgrade when the evidence quote is a restatement: it has a **future cue** and **no delivery cue**.
  - **Future cue,** on whole words of the normalized quote: `expect|expects|expecting|will|shall|plan to|plans to|planning to|aim to|aims to|intend|intends|anticipate|anticipates|on track|going forward|is expected to|are expected to|remain committed|should be`.
  - **Delivery cue:** `came in|stood at|delivered|achieved|reached|crossed|completed|commissioned|commenced|started|launched|received|reported|grew|declined|met|was|were|has been|have been|had|did`.
- Do **not** reuse `guidance._CUES`. It contains `guidance` and `target`, which delivery statements also use: "broadly in line with our guidance" is a delivery statement.
- Rationale: `"The later call restated the target; delivery is not shown yet"`.

### C. Below-target guard: applies to `kept` only

- **When it applies:** only when `p.kind == "quantitative"`, `p.target_low` is not None, and the promise quote (normalized) does not match a lower-is-better cue: `below|under|less than|lower than|at most|not exceed|no more than|cap|reduce|bring down|within|maximum`.
- **Numbers in the evidence quote:**
  - first remove period labels (reuse `grounding._PERIOD` or an equivalent) and 4-digit years `\b(?:19|20)\d{2}\b`;
  - then parse `\d[\d,]*(?:\.\d+)?`, with commas stripped.
  - When `p.unit == "%"`, only numbers immediately followed by `%` or ` percent` count.
  - Otherwise, only numbers within `[0.1 × target_low, 10 × max(target_low, target_high or target_low)]` count. They must be the same order of magnitude.
- **Decision:**
  - if no number counts, skip the guard (it cannot check);
  - if every counted number is `< 0.98 × target_low`, downgrade.
- Rationale: `f"The later figure ({max_counted}) is below the {target} target"`. Format numbers like the existing `_fmt`. `target` is `_target(p)` or an equivalent "50–60" form. Every number in the rationale comes from the promise or the evidence.

### Counting

`build_ledger` gains an optional `stats: dict | None = None` parameter. Each downgrade increments `stats["verdicts_downgraded"][reason]`, with reasons `other_period`, `restated` and `below_target`.

The pipeline passes its existing `guard` dict, so the dossier's `guard` carries `verdicts_downgraded`. `scripts/eval_research.py` adds one column, "Verdicts downgraded (period/restated/below)", summed in the total row. Keep the existing columns unchanged.

## Tests (`backend/tests/test_research_ledger.py`, `test_eval_research.py`)

Build fakes the way the existing judge tests do (FakeRouter returning a judgement whose evidence quote is on a later source page):

- **The three live cases above, as written:**
  - DIXON → pending + the restated rationale;
  - IDEA → pending + the below-target rationale containing "42";
  - INDIGO → pending + the other-period rationale.
- **Must stay resolved:**
  - kept with "June quarter's capacity growth came in at 3% … broadly in line with our guidance" for horizon "Q1FY27" (a matching period, no future cue, and "guidance" must not trigger B);
  - kept "Effective tax rate for FY26 stood at 22.6%." for "ETR for FY26 will be in the range of 20%-24%" (unit %, lo 20, hi 24);
  - kept with no numbers and no period ("This marks our 26th sequential quarter of revenue growth."; qualitative);
  - missed with a matching period stays missed.
- **Lower-is-better skip:** "bring net debt below 2,000 crore" (lo 2000) with evidence "net debt stood at 1,850 crore" stays kept.
- **Mixed delivery and future:** "We commissioned the plant in Q2 and will ramp up in Q3" stays kept (it has a delivery cue).
- **Counting:** `stats` counts per reason, and the pipeline dossier's `guard["verdicts_downgraded"]` is present.
- **Eval:** the new column renders and sums.

## Constraints

- TDD. Run `cd backend && uv run pytest -q`, `uv run ruff check .` and `uv run ruff format --check .`.
- Commit with a message ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No network. Never read `backend/.env`. No live builds.
- Do not change the judge prompt, extraction or computed grading.
