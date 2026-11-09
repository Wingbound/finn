# Plan 3 final-review fix wave: report

Branch `feat/pull-research`, from 4f5e3e7 to 7105070 (10 commits). Every brief item is done with tests. TDD throughout: each item's tests were added first and seen to fail (for example, C1 gave `45 failed, 86 passed` on `tests/test_research_ledger.py` before the gates existed).

## Verification (at HEAD 7105070)

```
$ cd backend && uv run pytest -q
727 passed in 3.17s
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
82 files already formatted
```

The baseline at 4f5e3e7 was 537 passed, so the wave adds 190 tests. Most come from parametrised cases.

The reviewer probes were re-run offline (`scratchpad/probe1.py` to `probe4.py`):

```
2 horizon==made_in computed: None
1b this-year in Q4 call: None
6 EBIT-as-EBITDA: None
6b delta-as-level: None
7 QoQ-as-YoY: None
3 negative net worth: D/E None ['Net worth is negative (−₹4,900 cr): debt exceeds the equity base']
4 forward_looking? False | Our new plant in Noida is operating at 80% utilisation today
4 forward_looking? False | As expected, revenue grew 15% this quarter on strong demand
4 forward_looking? False | We had targeted 15% growth and delivered 16% for the year
4 forward_looking? False | Customers are willing to pay a premium for our products now
4 forward_looking? False | The capacity was commissioned as planned in the last quarter
LLM down -> notes: [..., 'Guidance from Q2 FY27 earnings call (Oct 2026) could not be read (model unavailable)', ... x4, 'Snapshot unavailable (model unavailable)', 'Bull/bear unavailable (model unavailable)']
  ledger rows: 0 note: Guidance could not be read from 4 of 4 calls
probe3: 'FY27', 'by FY27', 'end of FY27', 'FY27 end', 'exit FY27', 'by the end of this fiscal', 'Q4 FY27', 'by March 2027', None -> pending (all)
probe3 prompt: horizon=next quarter (made in Q4 FY26; target period Q1 FY27)
probe4: NIM-as-ebitda_margin -> None (both lenders)
```

- Probe 1 item 5 now raises a TypeError, because the probe calls the private `_judge_one(raw, later)` with its old signature. I1 is covered by the tests listed below.
- Probe 2's two conditional sentences still return True from `_forward_looking`. That is expected: the cue check is separate, and the new conditional gate in `extract_promises` drops them (covered by `test_conditional_and_past_statements_dropped`).

## Commits

| SHA | Subject |
|---|---|
| 023b14e | fix(research): gate the computed ledger grade deterministically (C1) |
| 3938158 | fix(research): negative net worth gets a concern flag, never a debt-free one (C2) |
| 8e68186 | fix(research): grounded judge rationale, visible model failures, no degraded overwrite (I1, I2) |
| da62f40 | fix(research): keep live builds inside Vercel's 300 s limit (I3) |
| d9f25c7 | fix(research): drop conditional guidance, whole-word cues, period-aware judging (I4, I5) |
| 37227e6 | fix(research): page citations ground in their quote, credibility needs 3 resolved, done before save (I6, I7, I8) |
| 0564d0c | fix(research): review minors (lender FACTS label, empty P&L, judge rules, truncation, eval column) |
| e842a74 | docs: research design, evals and brief match the code after the review fixes |
| 8109c65 | fix(research): a bare year marks a long horizon only after a time word |
| 7105070 | fix(research): source-row notes in plain English, exception type in the log (I2) |

## Per item

### C1: computed-path gates (`ledger._gated`, called from `_grade`)

All seven gates send the promise to the judge (`_grade` returns None):

1. The period key must be greater than `_qkey(made_in)`. The new `_period_key` treats FYyy as (yy, 4), and `_not_yet_due` shares it.
2. A Q4 call with a relative-year horizon (`_REL_YEAR`).
3. The horizon must appear in the normalised quote (`_horizon_in_quote`):
   - FY27, FY 27, FY2027 and fiscal 2027 are equivalent, and Q3 FY27 matches Q3FY27;
   - a relative phrase must appear word for word.
4. Metric words, matched as whole words (`_METRIC_WORDS`).
5. Mismatch cues (`_MISMATCH`): ebit (not ebitda), qoq, quarter-on-quarter and quarter on quarter, sequential*, cqgr, constant currency, dollar*, usd, us$, $, bps, basis points, expan*, improv*, `by \d`.
6. A lender (`is_lender(annual)`) with an ebitda_margin target.
7. `financials.year_end_month(annual)` is not "Mar". I renamed it from the private `_year_end_month`; TTM is excluded.

Range targets now read "against a target of 15–18%"; otherwise the rationale says "at least 15%".

Tests (all in `tests/test_research_ledger.py`):

| Gate or behaviour | Tests |
|---|---|
| 1 | `test_gate_period_must_end_after_the_call` (4 cases, each with an earlier-call control) |
| 2 | `test_gate_relative_year_in_q4_call` (7 phrases, each with a Q3-call control) |
| 3 | `test_gate_horizon_must_be_in_quote` (5) and `test_gate_horizon_label_forms_match` (6) |
| 4 | `test_gate_quote_must_name_the_metric` (6) and `test_gate_metric_words_accepted` (10) |
| 5 | `test_gate_metric_mismatch_cues` (16) and `test_gate_ebitda_is_not_ebit` |
| 6 | `test_gate_lender_margin` and `test_lender_margin_is_judged_not_computed` (this replaces the old `test_compute_margin_lender`, which expected a lender margin to compute) |
| 7 | `test_gate_fiscal_year_must_end_in_march` (Dec year-end, TTM only, empty) |
| Probe 1 cases | `test_probe_cases_are_judged` |
| Range rationale | `test_computed_rationale_for_range` |

The existing computed tests still compute with unchanged assertions. Their quotes now come from `p_growth` and name the metric and horizon (for example, "We expect revenue to grow 15% in Q2 FY27"), and they pass a March P&L (`MAR` or `LENDER`).

### C2: negative net worth (`financials.balance_sheet_health`)

- When net worth ≤ 0, `debt_to_equity` is None, no D/E flag of either kind is raised, and the concern "Net worth is negative (−₹4,900 cr): debt exceeds the equity base" is added.
- The new `inr_cr()` puts the sign before the ₹. It is used in the FCF flag ("(−₹30 cr)") and in the FACTS FCF line.
- Tests: `test_negative_net_worth`, `test_zero_net_worth_is_flagged_without_de`, `test_flag_thresholds` (updated to −₹30) and `test_facts_negative_fcf_sign_before_rupee`.

### I1: grounded judge rationale (`ledger._judge_one`, `_rationale`)

- For kept, partly and missed, the LLM sentence is kept only if it is at most 30 words and `numbers_grounded(r, promise.quote + "\n" + evidence.quote)` holds. Otherwise the row reads "See the later evidence quote."
- Pending rows carry code strings only:
  - "Too recent to judge";
  - "Target not yet due — tracking is not delivery";
  - "No verifiable later evidence";
  - "No later evidence of the outcome yet".
- Dropped rows read "Not mentioned in the later calls".
- Tests:
  - `test_resolved_rationale_with_ungrounded_number_becomes_template`
  - `test_resolved_rationale_grounded_and_short_is_kept`
  - `test_resolved_rationale_over_30_words_becomes_template`
  - `test_pending_rationale_is_a_code_string`
  - `test_dropped_rationale_is_a_code_string`
  - `test_unknown_status_becomes_pending_with_code_rationale` (replaces the old truncation test)

### I2: visible LLM failures and no degraded overwrite

**Failure notes:**
- `extract_promises(..., notes=None)`, `snapshot(..., notes=None)`, `bull_bear(..., notes=None)` and `build_ledger(..., notes=None)` report an LLMError or an unusable reply shape:
  - "Guidance from {title} could not be read (model unavailable)";
  - "Snapshot unavailable (model unavailable)";
  - "Bull/bear unavailable (model unavailable)";
  - "Some promises could not be judged (model unavailable)".
- A stage crash now reads "{Stage} could not be built (internal error)", or "Guidance from {title} could not be read (internal error)". The exception type and message go to `log.warning` only.
- Unusable concall or AR rows in `collect_sources` follow the same rule: "Oct 2026 transcript skipped (unusable listing)".

**Empty ledger:** when 2 or more transcripts were read and the ledger has 0 rows, `ledger.note` is set:
- "No verifiable forward-looking guidance found in {n} calls"; or
- "Guidance could not be read from {k} of {n} calls" when extraction failed (model unavailable or a crash).

**Degraded builds:**
- `pipeline.is_degraded(d)` checks the notes for "model unavailable", "could not be built", "could not be read" or "skipped: build deadline reached".
- API `/build`: if the new build is degraded and the stored dossier is complete, nothing is saved. The stream sends "Live rebuild was incomplete; showing the last complete dossier", then `done` with the stored dossier.
- The CLI (`scripts/research.py`) does the same and prints "{SYM}: warning: rebuild incomplete (...); kept the stored dossier built ...".

**Tests:**
- Pipeline: `test_llm_down_everywhere_is_visible` (router raises LLMError everywhere: notes present, ledger note set, nothing raises), `test_empty_ledger_note_when_calls_have_no_guidance`, `test_guidance_crash_counts_as_unread`, `test_ledger_internal_error_note`, `test_stage_failure_becomes_note` (updated) and `test_is_degraded_markers`.
- Guidance and synthesis: `test_llm_error_and_bad_shapes_are_reported`, `test_model_failures_are_reported` and `test_valid_empty_replies_are_not_failures`.
- Ledger: `test_judge_failure_is_noted` (3) and `test_judge_success_adds_no_note`.
- API: `test_degraded_rebuild_keeps_stored_dossier` and `test_degraded_first_build_is_saved`.
- New `tests/test_research_cli.py` (3), including `test_cli_does_not_overwrite_with_a_degraded_build`.
- Docs: `test_collect_sources_odd_rows_skipped` and `test_collect_sources_invalid_url_skipped` (both updated).

### I3: the 300 s limit

- `collect_sources(..., deadline=None, now=time.monotonic)` checks the deadline before each transcript and before the annual report. Past it, it notes "Remaining sources skipped: build deadline reached" and stops.
- `build_dossier` uses `DEADLINE_MARGIN_S = 60`. Sources get `deadline = t0 + deadline_s − 60`, and every stage, guidance call and judge group needs at least 60 s left.
- `build_ledger(..., should_stop=)` is checked before each judge group. Once it returns True, the remaining groups stay pending ("Not assessed") and the note "Remaining promise checks skipped: build deadline reached" is added.
- `api_main._stream(q, clock)` waits with `q.get(timeout=min(15, left))`. On a timeout it yields `: ping\n\n`, and at 285 s it yields `event: error` with `{"detail": "build timed out"}`.
- Tests:
  - `test_collect_sources_stops_past_deadline`
  - `test_collect_sources_deadline_skips_annual_report`
  - `test_deadline_margin_skips_sources`
  - `test_deadline_stops_judge_groups`
  - `test_deadline_skips_llm_sections` (rewritten: the clock jumps once sources are read)
  - `test_should_stop_is_checked_before_each_judge_group`
  - `test_should_stop_never_blocks_rows_without_later_calls`
  - `test_stream_pings_while_waiting` and `test_stream_times_out_at_285s` (scripted queue with a fake clock: 18 pings, then the error at t = 285)

### I4: conditionals and past facts (`guidance.py`, `cite.py`)

- The system prompt adds: "Exclude conditional or hypothetical statements (if, unless, assuming, provided, subject to)."
- A promise is dropped when `_CONDITIONAL` matches its normalised quote or `cite.sentence_prefix(cite, source)`. That is the earlier part of the sentence at the occurrence `locate` accepts, built on the same `_prefixes` helper that `_found` now uses.
- Cues are whole words, exactly the brief's list. Past forms, prefix matches and "endeavour" are gone.
- Tests:
  - `test_conditional_and_past_statements_dropped` (10, covering every example in the brief, fragments included)
  - `test_plain_forward_statement_kept`
  - `test_forward_cues_whole_words` (43)
  - `test_past_forms_and_prefixes_are_not_cues` (9)
  - `test_system_prompt_excludes_conditionals`
  - `test_sentence_prefix`

### I5: periods on the judged path (`ledger.py`)

- Each prompt line carries "(made in Q1 FY27; target period FY27)" when `parse_horizon` resolves, and "(made in Q1 FY27)" otherwise.
- `_not_yet_due` takes the first period mentioned in horizon plus quote (`_scan_period`):
  - FY labels and quarter labels;
  - "march/mar 20yy", read as FY Q4;
  - this, current or next year/fiscal/financial year, and next or coming quarter, resolved from `made_in`. In a Q4 call the new FY has begun.
- A long horizon (`_long_horizon`) is any FY at least `LONG_YEARS = 2` past the newest call, plus the existing word cues.
- Tests:
  - `test_judge_prompt_states_made_in_and_period`
  - `test_lenient_period_scan_downgrades_kept` (9: by FY27, end of FY27, exit FY27, by March 2027, "by the end of this financial year", and more)
  - `test_lenient_scan_this_year_in_q4_call_means_next_fy`
  - `test_past_or_no_period_stays_kept`
  - `test_long_horizon_is_relative_to_newest_call` (FY29 with newest FY27 is long; FY28 is not)
  - `test_bare_years_but_not_amounts_are_long`

### I6: page citations ground in their own quote (`synthesis._validate`)

- A transcript or AR point uses `numbers_grounded(text, cit.quote)`; FACTS points still ground in their FACTS line. The prompt now says "Any number in your sentence must appear in the quote you cite."
- Test: `test_page_cited_point_grounds_numbers_in_its_quote_only`. A T1 point carrying the FACTS-only 18.2% is dropped.
- `test_bull_bear_cap_three_and_long_text_dropped` had passed only because its digits 0–4 appeared in the FACTS tally. Its texts now carry no numbers.

### I7: credibility on small samples

- `credibility_pct` is None when fewer than `MIN_RESOLVED = 3` promises are resolved.
- The FACTS line reads "Promise ledger: 3 kept, ... 0 dropped (6 of 10 promises resolved, credibility 62.5%)", or "(2 of 5 promises resolved)" with no credibility.
- Tests: `test_credibility_none_under_three_resolved`, `test_facts_ledger_line_without_credibility` and `test_facts_block_lines_and_skips_none` (updated).

### I8: worker ordering and excerpts (`api/main.py`)

- `_build_worker` queues `done` first, then saves; a save failure is logged only.
- An inner try handles the errors and closes the connection, and an outer `finally` always queues `_DONE`.
- `_done(d)` adds `excerpts: {source_id: {"page": text}}` for every cited page, FACTS excluded. It walks citations with the new `cite.dossier_citations`, which `scripts/eval_research.py` now reuses.
- Tests:
  - `test_build_streams_progress_then_done` (excerpts asserted)
  - `test_done_payload_has_excerpts_for_every_cited_page` (promise, evidence and bull citations; FACTS skipped)
  - `test_cached_done_has_excerpts`
  - `test_save_failure_still_streams_done`
  - `test_worker_puts_done_marker_even_if_close_raises`

### Minors

| Fix | Tests |
|---|---|
| The lender FACTS line reads "Financing margin change" | `test_lender_facts_say_financing_margin` |
| `fetch_company` uses `any(parse_table(...).values())` | `test_fetch_company_headers_without_rows_is_not_data` |
| The judge prompt adds "missed only if management cut, lowered or moved the target, or the stated time passed without it" | `test_judge_prompt_missed_rule` |
| Truncation: `cite.tag_pages` returns (text, truncated). The prompt lists "TRUNCATED (later pages not shown): ids." and tells the judge not to use dropped for those calls. `_judge_one` turns dropped into pending when any later call was cut | `test_truncated_evidence_is_flagged_and_blocks_dropped`, `test_untruncated_evidence_has_no_flag`, `test_dropped_needs_two_later_sources_and_no_evidence` (updated, see Concerns) |
| The eval table gains a "FACTS citations" column, totals included | `test_eval_report_has_columns` |
| The "found 0" ledger note is unchanged and now pinned | `test_no_transcripts_note` |

### Docs (e842a74)

**DESIGN.md:**
- :81 transcripts are read whole on Flash-Lite;
- :82 Flash-Lite with evidence gating;
- :86 per-ticker cache, 10-minute rebuild and the degraded rule;
- request-time exception, :107 and :110: the API is read-only except `/research/search` and `/research/{sym}/build`;
- :94 about 9 calls by design, with no cap; deadline checks with a 60 s margin; SSE ping and 285 s;
- :95 the exact grading rules and gates, as sub-bullets.

**PROJECT_BRIEF.md:** :190–191 Flash-Lite routing; :204 now names `scripts/refresh.py` and `scripts/research.py`.

**EVALS.md §4:**
- verification is 100% by construction;
- a hand audit of resolved rows is the fairness measure (results pending, controller);
- the drop rate covers the cue filter, the conditional filter, de-duplication and the 8-item cap;
- the budget wording and the FACTS column.

"Live results: pending (controller)" is left in place.

## Deviations

1. **C1 gate 4:** the metric words also accept plurals (revenues, net profits, operating margins), within the brief's intent.
2. **C1 gate 3:**
   - "fiscal 2027" and "fiscal year 2027" count as FY27;
   - an FY inside a quarter or half label ("Q3 FY27") or a span ("FY27-28") does not count as an FY27 horizon, so it is judged.
3. **C1 gate 7:** an annual table with no dated column counts as "not March" (fail safe). Tests that passed `annual={}` now pass a March P&L.
4. **C1 gate 5:** `by \d`, expan* and improv* apply to every metric, as the brief lists them. "We will grow revenue by 15% in FY27" is therefore judged, not computed.
5. **C2:** the net-worth flag renders "−₹4,900 cr", following the sign-before-₹ minor, not the literal f-string's "₹-4,900". The FACTS FCF line uses the same helper.
6. **I1:** "Not assessed" stays as a code string for rows the judge never returned: model failure, an id missing from the reply, or a deadline skip.
7. **I2, reply shape:** an unusable reply shape uses the same "(model unavailable)" note as an LLMError, since the brief maps both to that string. "could not be read" was added to the degraded markers so guidance failures count.
8. **I2, ledger note:** when failures explain an empty ledger, `ledger.note` reads "Guidance could not be read from k of n calls". This reconciles "unless a model-unavailable note explains it" with the test spec's "ledger note set".
9. **I2, keeping the stored dossier:** a degraded rebuild keeps the stored dossier only when the stored one is complete. If the stored one is degraded too, the newer build is saved; otherwise "last complete dossier" would be untrue and a stale degraded dossier would stick.
10. **I2, odd source rows:** the plain-English rule was extended to `collect_sources`' odd-row notes, which used to print exception types.
11. **I2/I3, note wording:** stage notes are capitalised ("Snapshot skipped: build deadline reached", "Bull/bear skipped: ...").
12. **I5:** the lenient scan also resolves next year/fiscal/quarter. A bare calendar year counts towards a long horizon only after a time word (by, in, till, ...), so "Rs 2075 crore" is not FY75 (8109c65).
13. **I8:** excerpts are also on the cached `done` and the kept-stored `done`.
14. **Truncation note:** placed as one line after the EVIDENCE header, not inside each block, so each source's budget stays exact.
15. **PROJECT_BRIEF.md :190:** also corrected, since :191 could not be made accurate alone. `extract_pdf` is configured but unused, and results come from XBRL.

## Concerns

- **The truncation rule bites on real data.** With 3 later calls, each source gets 66,666 chars, and the PERSISTENT Q1 FY27 transcript is 71,036 chars. Promises from the oldest call can therefore never be "dropped"; they become pending. This works as specified, but the controller may want a larger `JUDGE_EVIDENCE_CHARS`.
- **Computed coverage will fall.** The quote must now name both the metric and the period, and the deviation-4 cues apply to every metric. Expect most live promises to be judged.
- **The SSE timeout ends the stream, not the build.** The worker thread keeps running and may still save (or keep) the dossier.
- **The 9-call budget is not enforced** by any code.
- **PROJECT_BRIEF.md :194** still says "Hugging Face Spaces (Docker)". It is stale but outside the brief's list, so I left it.
- The probe scripts call private helpers. Probe 1 needs updating to the new `_judge_one(raw, later, p)` signature.

No network, live builds, `backend/.env` or `backend/seed/` were touched.
