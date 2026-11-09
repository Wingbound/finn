# Task 7g report

Commit 83d14c3. Full suite 753 passed; ruff check and format clean.

## Changes
- ledger.py: `_other_period`, `_restated`, `_below_target`, `_guard_verdict` (runs in `_judge_group` after `_judge_one`, before `_not_yet_due`). `build_ledger(..., stats=None)` initialises `stats["verdicts_downgraded"]` with zeros for other_period/restated/below_target and counts each downgrade.
- pipeline.py: passes `stats=guard`.
- eval_research.py: new column "Verdicts downgraded (period/restated/below)", summed in total row.
- Tests (test_research_ledger.py): test_guard_dixon_restated_target_is_pending, test_guard_idea_below_target_is_pending, test_guard_indigo_other_period_is_pending, test_guard_leaves_valid_verdicts (5 cases), test_guard_lower_is_better_skips_below_target, test_guard_fy_horizon_other_fy_downgrades_and_quarter_only_passes, test_guard_stats_count_each_reason. test_eval_research.py: test_eval_downgrade_column_renders_and_sums; test_guard_recorded_on_dossier now expects the verdicts_downgraded key (pipeline dossier check).

## Deviations
- Below-target rationale omits "%" unless unit is %: "The later figure (42) is below the 50–60 target" (existing `_target` always appends % so not reused).
- Existing tests adjusted because the new guards correctly bite on their fixtures: test_judged_kept_with_page_corrected now uses status "missed" (its quote "we intend replacing..." is a restatement); test_future_horizon_pending_past_horizon_kept uses horizon Q2 FY27 (evidence is a Q2 FY27 quote).
- The guard only runs when a verdict has evidence; B skips missed.

## Concerns
- `ruff format .` may have reformatted untracked scripts/export_fixtures.py (not staged).
- `_PERIOD_LABEL` is a local regex (grounding._PERIOD lacks FY with apostrophe/space).

## Fix round 1
- Below-target guard strips fused/spaced period labels (H1FY26, Q3 FY'26, 9MFY26) before parsing numbers.
- Present-tense number ("is/are/stands/now [at] [Rs] N") counts as delivery, so the restated guard skips it; DIXON still downgrades.
- Weak delivery words followed by an intention (had planned, was expected, ...) are removed before the delivery-cue check.
- test_judged_kept_with_page_corrected is a kept verdict again, on a delivery sentence (REAL_T1_C) on page 7.
- Rationale now "The later figure (42) is below the target (50–60)".
- New tests: test_guard_fused_period_label_is_not_a_number, test_guard_present_tense_number_is_delivery, test_guard_dixon_still_downgrades_with_present_tense_rule, test_guard_weak_delivery_cue_before_intention_is_restated. 757 passed, ruff clean.
