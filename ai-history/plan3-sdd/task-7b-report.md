# Task 7b report

## Implemented
- A ledger.py: judge evidence is tagged_text(src, 90_000) per later source (headers and order kept); prompt says search all later calls, prefer most recent mention. Removed unused _terms/_METRIC_WORDS/relevant_window.
- B config.py: finn_model_reason = gemini-3.5-flash-lite (comment explains 3.8 flakiness); FALLBACKS reason and extract_transcript = [gemini-3.1-flash-lite]. extract_pdf unchanged.
- C guidance.py: forward-looking-only rule added to SYSTEM.
- D synthesis.py: bull/bear accept source_id FACTS (quote equals a FACTS line after normalize, or 3+ word substring of exactly one line); stored Citation(FACTS, 0, full line); numbers grounded in that line only. Snapshot rejects FACTS. Prompt updated. Citation docstring in models.py.
- E pipeline.py: new progress text; MAX_TRANSCRIPTS constant added to docs.py (default of collect_sources) and used by pipeline.

## Tests
New: ledger whole-transcript test, guidance prompt test, 4 FACTS tests, chain_for reason/transcript test; updated chain dedupe test, pipeline progress assertion, and the Gemini safety-block test (now has a second gemini fallback to mock).
Final: `uv run pytest -q` 519 passed; ruff check clean; ruff format --check clean.

## TDD
RED (`uv run pytest -q` after tests, before code): 6 failed, 513 passed - test_chain_for_dedupes_primary_and_fallback, test_chain_for_reason_and_transcript, test_system_prompt_forward_looking_only, test_judge_prompt_includes_whole_later_transcript, test_build_end_to_end, test_bull_facts_citation_kept_with_full_line.
GREEN: `uv run pytest -q` -> 519 passed.

## Files
backend/finn/{config.py,models.py}, finn/research/{ledger,guidance,synthesis,pipeline,docs}.py; tests: test_llm_router, test_research_{ledger,guidance,synthesis,pipeline}.py. One commit on feat/pull-research.

## Self-review / concerns
- Full transcripts (up to 90k chars each, 3 later calls) make judge prompts large, perhaps 60k+ tokens; Flash-Lite free-tier TPM may be a risk. Grouping is per source so call count is unchanged.
- Only FACTS bull/bear quotes that are exact lines or unique 3+ word substrings are kept; some flag lines are prose, so unusual paraphrases get dropped (safe).
- Two bull/bear FACTS tests use `# fmt: skip` long lines.
- Gemini now has no non-Gemini fallback for transcripts: a Gemini-wide outage fails extraction.

## Task 7c
Changes (finn/research/ledger.py): (1) SYSTEM status definitions replaced per ruling, plus the two verbatim sentences on reaffirming and outcome quotes; (2) _judge_one sets evidence None when final status is pending; (3) JUDGE_EVIDENCE_CHARS = 200_000, per-source cap min(90_000, budget // n_later).
Tests added in tests/test_research_ledger.py: test_system_prompt_reaffirming_rules, test_pending_rows_carry_no_evidence (pending/kept/partly/missed), test_judge_evidence_total_budget (3 sources, each <= 66_666, prompt <= 200_000 + headers).
RED: `uv run pytest -q tests/test_research_ledger.py` -> 3 failed, 61 passed (reaffirming rules, pending-False, budget ImportError of JUDGE_EVIDENCE_CHARS).
GREEN: `uv run pytest -q` -> 525 passed; ruff check and format --check clean.

## Task 7d
Changes: guidance.py `_CUES` regex (prefix cues expect/target/guid/aim/plan/intend/aspir/anticipat/commit/endeavo(u)r; whole-word cues will, shall, would, outlook, going forward, on track, by fy, next, upcoming, should, likely, confident, look to, looking to, look forward) applied after locate; quotes with no cue are dropped (covers the "If ..." conditional). ledger.py: `_SEGMENT` regex makes `_grade` return None (judged); `_not_yet_due` downgrades judged kept/partly to pending (rationale "Target not yet due — tracking is not delivery", evidence None) for long-horizon cues (`_LONG`) or horizon sorting after newest later source (FY = Q4 of that year); same-metric-and-period sentence added verbatim to SYSTEM.
Tests added: test_future_cue_required, test_segment_promise_judged_not_computed, test_long_horizon_kept_becomes_pending (2 cases), test_long_horizon_missed_stays_missed, test_future_horizon_pending_past_horizon_kept, test_same_metric_period_sentence. Existing guidance tests' TAX quote (a past fact, now correctly dropped) replaced by a forward-looking fixture sentence (target 25).
RED: `uv run pytest -q` -> 6 failed, 531 passed (test_future_cue_required, test_segment_promise_judged_not_computed, both long_horizon kept cases, test_future_horizon_pending_past_horizon_kept, test_same_metric_period_sentence).
GREEN: `uv run pytest -q` -> 537 passed; ruff check clean; ruff format --check clean.
