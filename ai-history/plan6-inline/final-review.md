# Plan 6 final review: b1b5d61..ed5235e (feat/one-loop)

Reviewer: final whole-branch review. This was a read-only pass, done in three passes: the diff, the five Review Focus items, and probes against the real seed and against realistic quotes.

## What I ran

- `cd backend && uv run pytest -q` gave 837 passed. `uv run ruff check .` was clean.
- `cd frontend && npx vitest run` gave 193 passed. `npx tsc --noEmit` and `npx eslint .` were clean. `npx playwright test` gave 35 passed and 24 skipped (the skips are the screenshot specs, which need `SCREENS`).
- `scripts/eval_research.py --db <copy of seed>` gave 510/510 citations. The ledger is 21 kept, 0 partly, 2 missed, 306 pending and 3 dropped, with 2 rows computed and 330 judged. Downgrades: 1 period, 13 restated, 3 below, 1 measure, 1 meets.
- Probe scripts lived in the session scratchpad (`probe/*.py`) and ran against a copy of the seed:
  - `real.py` takes each holding's real latest card and prints the promise notes it would get;
  - `sim.py` forces a covering card for every pace-eligible promise;
  - `gates.py` and `gates2.py` run realistic quotes through `pace_note` and `_target`;
  - `guards.py` runs realistic evidence through the ledger guards;
  - `judged2.py` replays the cached judge replies in `backend/data/build6.sqlite` through the current guards;
  - `rank.py` compares the current ranking with the plan's rule.
- I loaded `ledger.py` from b1b5d61 and ran it side by side with the branch's version to check the regression in I6.

## Strengths

- **Review Focus 1–5 all hold on the real data.**
  1. A results story with no dossier gets `promises: []`, and `PromisePanel` returns null, so the DOM is unchanged.
  2. Only `pending` rows are selected, so resolved and dropped rows never appear as open.
  3. Lender cards (`nbfc`, `bank`) have no `ebitda_margin` row, so no margin pace is possible.
  4. AUM and PRASK quotes fail the revenue-word gate (BAJFINANCE 20–24% AUM, INDIGO PRASK).
  5. `/research/HDFCBANK`, IDEA, INDIGO, POLYCAB and DIXON return `latest_results: null`, and `DossierView` leaves the section out.
- **The only pace sentence in the data is correct.** It is ZYDUSLIFE: 24.0% EBITDA margin beside "24% plus … FY27". Its period is in the quote, and the card's EBITDA is not one of the two definition misses.
- **Guard downgrades on real data are right.** Replaying 58 cached judge verdicts, every downgrade the guards make in the seed (13 restated, ULTRACEMCO's tons against MW, ZYDUSLIFE's 24% "meets") is a correct downgrade. MAXHEALTH's slipped "this quarter" beds and LODHA's restated 20% PAT are good catches.
- **Corrupt dossiers can't 500 the digest.** `attach_promises` catches `ValidationError`, `ValueError` and `DatabaseError` per symbol and caches per symbol.
- **Reading the dossiers per request is cheap.** Loading and validating all 23 seed dossiers (8 MB of JSON) takes 39 ms, so the per-request read on Vercel is not a concern at 18 holdings.
- **The atomic seed copy is right.** It copies to a temp file, renames, and runs in `finally`, behind the existing `_seed_lock`. The test reproduces the truncation.
- **Docs mostly match the code and data.**
  - 510/510 citations; 23 dossiers = 18 holdings + 5;
  - 21 kept / 2 missed / 3 dropped; 306 pending; 2 computed;
  - 19 downgrades split 1/13/3/1/1;
  - 6 results stories with 3 notes each in `digest-7d.json`, with the pace firing once.
- **Copy rules hold.** Quotes are in `.quote` (Literata) and FINN's words in Plex. The labels are sentence case. "See the ledger" and the citation chips are 44 px. The live region moved to the progress lines only.

## Critical (must fix)

None. Nothing is broken, and the one pace sentence shipping today is correct. The Important items are about what a reader sees now on Today (I4, I5) and about gates that will meet new guidance every quarter (I1–I3, I6, I7).

## Important (should fix)

### I1. The pace sentence states a target number that need not be in the quote
- **File:** `backend/finn/research/link.py:121-153` (`pace_note`), rendered by `frontend/src/components/today/PromisePanel.tsx:9-16`.
- **What's wrong.** `_target()` hides the target label unless its numbers and unit are in the quote (Task 1 and Task 3 rulings), but `pace_note()` uses `p.target_low`/`p.target_high` without that check. The sentence repeats the number in FINN's words, so the grounding rule is bypassed exactly where it matters most.
- **Failing scenarios** (`gates.py`; card revenue +21.6% YoY, Q2 FY27):
  - "We expect double-digit revenue growth in FY27." with lo=10 shows no target label, but "This quarter: revenue +21.6% YoY, at or above the 10% target."
  - "We expect mid-teens revenue growth in FY27." with lo=15 gives "…at or above the 15% target."
  - The extractor carries 15–18 for "…in FY27, about 20 to 25%". The label is hidden, but the pace says "above the 15–18% target", which contradicts the quote beside it.
- **Fix.** In `pace_note`, return None unless `_target(p)` is not None. That one call checks grounding and unit, and it costs nothing on current data. Also take "at or above" from the same open-endedness test, so a point target ("24% EBITDA margin") isn't silently treated as a floor.

### I2. The pace gates match a different measure that shares a word with the line
- **File:** `backend/finn/research/link.py:27-36` (`_LINES`), `:126-132`. Plan Global Constraints, "Pace gates".
- **What's wrong.** The gates test only whether words co-occur anywhere in the quote. The extractor's `metric` enum has no PAT-margin, same-store or unit-revenue value, and the executor already saw it file AUM and PRASK as `revenue_growth`, so these labels are likely. Each case below fires a pace note on the wrong line (`gates.py`, `gates2.py`):

| Quote (metric) | What the reader sees |
|---|---|
| "We expect PAT margin of 12% in FY27." (`pat_growth`) | "PAT +16.2% YoY, at or above the 12% target": a margin target beside a growth rate |
| "…net profit margin of 12% for FY27." (`pat_growth`) | same |
| "We expect sales volume growth of 15 to 18% in FY27." | revenue growth beside a volume target |
| "Same-store sales growth of 15 to 18% in FY27." | total revenue beside an SSSG target |
| "export sales to grow 15 to 18%" / "Domestic formulation sales should grow…" | consolidated revenue beside a region (no `_SEGMENT` word) |
| "Organic revenue growth, excluding the acquisition, should be 15 to 18%" | reported (acquisition-inclusive) revenue beside organic |
| "passenger revenue per available seat kilometre to grow 15 to 18%" / "Unit revenue should grow…" | PRASK spelled out passes Focus 4's gate |
| "We expect AUM growth of 15 to 18% in FY27, and revenue growth should track it." | AUM target beside revenue |
| "We expect operating margin of 15 to 18%" (IT usage = EBIT) | EBITDA margin beside an EBIT target |
| LODHA, real (Q3 FY26): "…presales … with an embedded EBITDA margin of approximately 33%" (`ebitda_margin`, FY26) | Fires on any FY26 card (`sim.py`). Embedded margin on presales is not P&L EBITDA, and developers repeat this guidance every year. |
| "We expect H2 revenue growth of 15 to 18%." (horizon "FY27") | a half-year target beside Q2 |
| "…15 to 18% for FY28." (horizon mislabelled "FY27") | wrong year |

- **Fix.** Gates in this order:
  - **Blocklist.** Add a pace-only blocklist next to `_MISMATCH`: `margin` for the PAT and revenue lines; `volume`, `same[- ]store|like[- ]for[- ]like|sssg`, `per (?:available )?seat|unit revenue|realis|per (?:unit|ton)`, `aum|loan book|advances|disburs|book`, `export|domestic|international|india business|us business|north america`, `organic|excluding|ex-|inorganic`, `embedded|pre-?sales|bookings`, and `adjusted|normali[sz]ed|exceptional`.
  - **Adjacency.** The target number must sit within about 8 tokens of the line word.
  - **Period in the quote.** Require `ledger._horizon_in_quote(p.horizon, hz, quote)`, the check the ledger's own computed grade already uses. On today's data this costs nothing: the two pace-eligible current-year promises (ZYDUSLIFE Q2 FY27, LODHA Q1 FY27 PAT) both state the period.
- **Tests.** Add the table rows as parametrized cases to `test_no_pace_when_a_gate_fails`.

### I3. A Q4 call's "this year" or "next year" resolves to the wrong fiscal year
- **File:** `backend/finn/research/link.py:45-51` (`_covers`), which calls `ledger.parse_horizon`.
- **What's wrong.** `parse_horizon` maps "this year" in a Q4 call to the year just ended. The ledger knows this is ambiguous: `_gated` refuses relative years from Q4 calls (`ledger.py`, the `made[1] == 4 and … in _REL_YEAR` line), and `_scan_period` reads "this year" in a Q4 call as the new FY. `link._covers` uses `parse_horizon` without that guard.
- **Real data** (Q4 FY26 calls, held in April and May 2026), each resolved to FY26:
  - TATASTEEL "2 million tons plus for this financial year compared to the previous financial year";
  - DIXON "beginning of Q4 this fiscal";
  - IDEA "this financial year";
  - TVSMOTOR "this year".

  These are FY27 promises, ranked as stale.
- **Failing scenario.** In May 2027 the Q4 FY27 card is on Today, and the dossier, rebuilt after the Q4 FY27 call, holds "This year we expect revenue growth of 15 to 18%" (horizon "this year"). The pace note fires (`gates.py`, card relabelled Q4 FY26 → Q4 FY26 call): "This quarter: revenue +9.0% YoY, below the 15–18% target." That sets FY27's last quarter beside FY28 guidance, a wrong-period reading presented as pace.
- **Fix.** In `_covers` (and therefore `_rank`), return False when `_qkey(p.made_in)[1] == 4` and `_horizon_text(p.horizon) in _REL_YEAR`, mirroring `_gated`. Better still, fix `parse_horizon` to follow `_scan_period`'s convention, so the ledger and the loop agree.

### I4. Relative horizons are shown verbatim on a later card, so the reader gets the wrong period
- **File:** `frontend/src/components/today/PromisePanel.tsx:18-23` (`meta`).
- **What's wrong.** The horizon is printed as the extractor wrote it, prefixed with "By". On a card months later, "next quarter" or "next year" reads as relative to today.
- **Real notes on the current cards** (`real.py`):
  - SUNPHARMA, Q2 FY27 card: "Q1 FY27 call, p. 7. By next quarter." Next quarter from that call is Q2 FY27, this very card; the reader takes it as Q3.
  - MAXHEALTH: "Q1 FY27 call, p. 2. By this quarter." That quarter has passed, and the ledger says the beds slipped to post-Diwali.
  - AMBER: "Q3 FY26 call, p. 10. By next year." This means FY27, the current year; the reader takes it as FY28.
  - TECHM "Target 30%, next year.", IDFCFIRSTB "Target 15–20%, next year." and TVSMOTOR "Target ₹3,500 cr, next year.": all from Q4 FY26 calls, all meaning FY27.
  - The "By" prefix also produces ungrammatical or wrong copy: "By 18 months." (VOLTAS: *in* 18 months), "By post Diwali puja.", "By next nine months.", "By summer season." (VOLTAS: summer 2026, already over), "By Q3 and Q4".
- **Fix.** Server side, add `horizon_label` to `PromiseNote`:
  - the resolved label ("FY27", "Q2 FY27") when `parse_horizon` resolves, excluding the I3 case;
  - otherwise the phrase in quotes, tied to the call: `"next nine months", said on the Q1 FY27 call`.

  Drop the "By" prefix. Optionally skip (or mark "was due Q1 FY27") rows whose resolved horizon ended before the card's period. Also add "this quarter" and "current quarter" to `parse_horizon`.

### I5. The target label calls any extracted number a "Target", including a reduction
- **File:** `backend/finn/research/link.py:90-118` (`_target`), `PromisePanel.tsx:20`.
- **What's wrong.** `numbers_grounded` proves the number is in the quote, not that it is the target.
- **Failing scenario (real).** TVSMOTOR shows "Q4 FY26 call, p. 11. Target ₹500–600 cr, next year." beside "Next year, the investments will be much lower. It will be maybe another INR500 crores, INR600 crores lower than this INR 2,400…". The spend the quote implies is about ₹1,800–1,900 cr; ₹500–600 cr is the cut. The label contradicts the quote it sits beside, which the Task 1 ruling exists to prevent.
- **Same wording on non-goals.** "Target" also lands on things that aren't goals: PERSISTENT "Target $650 mn" (a deal's total contract value) and "Target $25–30 mn" (Nagarro transaction costs); PREMIERENE "Target ₹240–250 cr" (quarterly depreciation); SUNPHARMA "Target 25%" (tax rate).
- **Fix.**
  - Suppress the label when a comparative follows the number within a few words: `lower|higher|more|less|than|increase|decrease|reduction|savings`.
  - For `metric in ("capex", "other", None)`, use neutral copy such as "Figure said: ₹3,500 cr", or "Guided" for capex. Keep "Target" for the three results lines and `order_book`.
  - Add the TVS sentence as a test.

### I6. `_restated` regression: delivered evidence is now downgraded with a false "restated" rationale
- **File:** `backend/finn/research/ledger.py:428-449` (`_FUTURE`, `_DELIVERED`, `_MODAL_VERB`), `:490-494` (`_restated`).
- **What's wrong.** The branch added "should", "would", "scheduled" and bare "due to" as future cues. It removed was, were, had and did from the delivery words, and strips "to <verb>". Any delivered sentence that uses a past verb outside the 16-word list now counts as a restatement once a second clause looks ahead, or once it gives a cause with "due to".
- **Failing scenarios.** On b1b5d61 none of these is downgraded; on this branch all are downgraded, with the row showing "The later call restated the target; delivery is not shown yet" (`guards.py`, plus `ledger.py` from b1b5d61 loaded side by side):
  - "EBITDA margin improved to 24.5% in Q2 due to better product mix."
  - "Revenue increased 18% due to strong volume growth."
  - "The new capacity came on stream as scheduled."
  - "We added 300 beds this year and should add 200 more next year." This is a clean "kept" for a "300 beds this year" promise.
  - "Revenue rose 21% year-on-year, and we should do better in the second half."
  - "We were able to complete the 5 GW line, and production will ramp up next quarter." ("to complete" is stripped as a modal.)

  The three sentences the brief asked about ("We commissioned the plant in Q2 and will ramp it up", "Revenue was ₹500 crore, up 18%", "The 5 GW line was completed and is set to run at full capacity") are correctly left alone. No row in the current 23 dossiers is hit (the 13 replayed restated downgrades are all correct). Every new build on the public site runs this guard, though, and a wrong downgrade also lowers the resolved count toward `MIN_RESOLVED`, which hides credibility.
- **Fix.**
  - Drop bare `due to` (keep `due (?:for|in|by)`).
  - Treat `scheduled` only as `(?:is|are) scheduled (?:for|to)`, never "as scheduled".
  - Add common past verbs to `_DELIVERED`: `rose|increased|improved|expanded|added|opened|closed|went live|came on stream|operationali[sz]ed|exceeded|surpassed|touched|doubled`.
  - Limit `_MODAL_VERB`'s `to` branch to `(?:expected|planned|scheduled|set|due|going|likely) to`.
  - Pin each sentence above as a regression test.

### I7. `_restated` false negatives: an adverb after the modal hides a restatement
- **File:** `backend/finn/research/ledger.py:446-449` (`_MODAL_VERB`).
- **What's wrong.** The modal strip removes only the modal plus one word (or be/get/have been plus one word). With an adverb in between, the participle survives and counts as delivery, so a judge's wrong "kept" stands. That is the error class the second audit found at MAXHEALTH, which was caught only because its sentence had no adverb.
- **Failing scenarios.** None of these is caught:
  - "The balance 140 beds will also be commissioned post Diwali."
  - "The second line will now be completed in Q4."
  - "The plant should hopefully be commissioned by March."
  - "The new block is expected to be fully commissioned in Q3."

  The judge's "kept" stays kept, and the ledger shows a delivered promise that has slipped.
- **Fix.** Allow `(?:\w+ly\s+|also\s+|now\s+|soon\s+|then\s+|still\s+)*` between the modal and the optional `be`/`get`/`have been`, and again before the verb. Add these four sentences as tests.

## Minor

### M1. "Meets" and "below" rationales can state something false
- **File:** `ledger.py:514-528` (`_meets_target`), `:531-547` (`_below_target`).
- **Meets.** The 0.98 tolerance lets the message say "meets" for a figure under the target:
  - "EBITDA margin for the year was 23.6%" against "at least 24%" gives "The later figure (23.6%) meets the target (at least 24%)";
  - "Revenue grew 14.8%" against 15–18% gives "…meets the target (15–18%)";
  - an unrelated figure ("Our market share is now 31%") also "meets" a 15% growth target.
- **Below (already shipping).** The new ZYDUSLIFE dossier shows "The later figure (20) is below the target (200–400)" for an outperform-by-200–400-bps promise that the extractor stored as `%`.
- **Fix.** Keep the tolerance for the downgrade, but word the message "is at or near the target" unless `n >= lo`. In both functions, require the unit in the quote (reuse `link._UNIT_IN_QUOTE`).

### M2. Ranking ignores "an FY two or more years past the card's" (plan deviation)
- **File:** `link.py:166-176` (`_rank`) uses only `_LONG_WORDS`, while the plan's Task 1 selection rule also counts far fiscal years.
- **Effect** (`rank.py`):
  - PERSISTENT's card shows "…reduce down to 1X by FY2030" in place of "We expect the deal closure by Q4-CY26 or Q1-CY27";
  - M&M shows the FY30 pre-sales target ahead of nearer ones.
- **Fix.** Use `ledger._long_horizon(text, card_fy)`.

### M3. De-duplication keeps the copy without the pace note
- **File:** `link.py:185-195`.
- **Effect.** LODHA's card keeps the Q2 FY27 copy, "we expect to easily beat our profit guidance of 20% growth" (no pace, because "profit" alone isn't the PAT word). It drops the Q1 FY27 copy, "guidance for fiscal '27, that is 20% growth on last year's PAT", which would give "This quarter: PAT +28.3% YoY, above the 20% target."
- **Fix.** Among duplicates, prefer the row with a pace note, then a grounded target, then the newer call.

### M4. Pace copy is wrong for quarter targets
- **File:** `PromisePanel.tsx:15`, `link.py:144-152`.
- **Quarter horizons.** When the horizon is the card's own quarter, the reading is the outcome itself. "One quarter, not the full year." is then false, and "above the target" is in effect a verdict the ledger hasn't given. Fix: for quarter horizons, say "Target set for Q2 FY27", or leave the pace out and let the ledger compute the grade.
- **Edge cases.** A reversed range (lo=18, hi=15) gives "above" for 16 and prints "18–15%". Flat guidance (lo=hi=0) gives "above the 0% target". Fix: normalise the range, and skip the pace when `target_low <= 0`, as `_grade` does.

### M5. No test that a corrupt dossier gives no notes
- **File:** `backend/tests/test_link.py`. The plan's Task 1 says "A missing or corrupt dossier gives no notes"; the code handles it, but no test writes a bad `payload_json` and checks that the digest still returns 200.

### M6. Panel accessibility and quote truncation
- **File:** `PromisePanel.tsx:29-34`.
- **Heading.** The `<h4>` skips levels: Today has an h1, and story cards have no h2 or h3. It also repeats the section's `aria-label`; use `aria-labelledby` on an h2 or h3.
- **Clamp.** The 3-line clamp hides the very number the label states. In the README screenshot, ZYDUSLIFE's quote stops at "we are on track to deliver …", so "24% plus EBITDA margin" is cut while "Target at least 24%" shows below it. Today offers no way to expand the quote and no tappable citation. Fix: tap to expand (`<details>`, or a "More" button of 44 px), or render the call as a `CitationChip`.

### M7. Docs drift
- `docs/EVALS.md:411` says "Of 330 ledger rows"; there are 332 (330 judged plus 2 computed).
- `docs/EVALS.md:425` (Limits) still says "three deterministic guards"; there are now five.
- `docs/screenshots/loop-light.png` shows superseded copy, "at or above the target of at least 24%" (changed in b00ebf8 to "the 24% target").
- The plan asked for each build's time and cost in EVALS. EVALS gives only totals, and the stored dossiers now show the cached rebuild ("Served from cache"), so per-build cost appears nowhere.

### M8. Dossier "Latest filed quarter" edge copy
- **File:** `DossierView.tsx:39`.
- TRENT, which has no promises, reads "set beside the promises above".
- The live-build `done` payload carries no `latest_results`, so the section appears only after a reload. Either word the line conditionally and add `latest_results` to the `done` event, or say so in the type comment.

### M9. Promises about another company lead a holding's card
- On M&M's Q2 FY27 card, note 1 is the Tech Mahindra 15% EBIT-margin target ("Target 15%, FY27"). It sits right under M&M's own EBITDA-margin row, and the next note is a Mahindra Lifespace pre-sales target.
- The quotes do name Tech Mahindra and EBIT, so this is a ranking problem rather than a falsehood.
- **Fix.** Rank last any quote that names another listed entity or `subsidiar|associate|group company`.

## Declined to judge

- **Judge quality.** Whether the judge's reading of weak but on-topic evidence is right (the 9 "debatable" verdicts). That is LLM judgement, outside a code review; I checked only that the deterministic guards fire as documented.
- **Hand-audit counts.** EVALS gives 14/9/0 overall and 9/6/5 for the new verdicts. Confirming them needs a full manual re-audit. I replayed cached judge replies only to check each guard's firing.
- **First-build cost and time.** The 16 first builds ($0.93, 136 calls, 62–85 s): the stored dossiers carry the cached rebuild's cost, and no log in the repo records the first builds.
- **"All 516 re-verified".** The figure before the second round of checks can't be reproduced from the current seed.
- **Inline chip layout.** The visual effect of 44 px `CitationChip`s inside running text (line height in Points and Ledger rows) needs a design look at fresh screenshots.
- **The `#ledger` anchor.** Whether "See the ledger" scrolls to the ledger after the client-side dossier load. I didn't drive a browser, and the ledger is the first section anyway.
- **Rename atomicity on Vercel.** Whether `Path.replace` is atomic on Vercel's writable filesystem is platform behaviour, not verifiable locally.
- **Screenshot regeneration.** The `SCREENS=…` spec was not run.

## Verdict

**Ready to merge: With fixes.**

The loop is built as planned, and the five Review Focus items hold on the real data. The one pace sentence shipping today is correct, tests, lint, types and e2e are green, and the docs' main numbers check out against the seed.

Two things should be fixed before main (which is public) takes this branch:
- **What Today shows today.** Relative horizons mislead about the period (I4), and the TVSMOTOR "Target ₹500–600 cr" contradicts its quote (I5).
- **The ledger guard regression (I6).** It downgrades plainly delivered evidence on every new build.

I1–I3 and I7 are small regex or gate changes in the same files. They should go in the same pass, because every results season pushes new guidance through these gates, and each one is a way a pace sentence or verdict could put a wrong number, line or period in front of an investor.
