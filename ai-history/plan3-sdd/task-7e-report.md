# Task 7e report
Commit: e4705e6

## Changed
guidance.py: _CUES gains two alternations (passive/predicative future "is/are/be/being/remains/stays + expected/planned/... + to/for", and "expected/planned/scheduled/slated (to be) commissioned/completed/operational/launched"). Conditional gate untouched. Added two parametrized tests in test_research_guidance.py.

## RED
5 failed, 81 passed (all five passive-future cases failed; the four negatives already passed).

## GREEN
736 passed; ruff check clean; ruff format --check clean (82 files).

## Concerns
The cue "set to" and "due to" broaden matching, so "due for" or "is set for" count as forward-looking. "is estimated to" may match present-tense estimates ("revenue is estimated to be 5 cr"). Re-check the live drop rate.

## Fix round 1 (commit 6b4cd94)
Removed the second _CUES alternative (expected/planned/... + participle), which let past passives through. Added 4 required-False tests for the reviewer's sentences. The first pattern still covers "is expected to be commissioned".

Output:
- tests/test_research_guidance.py: 90 passed
- full suite: 740 passed
- ruff check: All checks passed!
- ruff format --check: 82 files already formatted

## Task 7f (commit 7600d70)
Changed: finn_model_reason default gemini-3.5-flash; FALLBACKS["reason"] = [3.5-flash-lite, 3.1-flash-lite]; UNPRICED_MODELS = {"gemini-3.5-flash"} in costs.py (no warning, cost 0.0); tests updated (default-model pricing, new no-warn test, chain_for reason); DESIGN.md routing and EVALS.md section 4 A/B line.

RED (tests/test_llm_router.py): 3 failed, 45 passed (default-model price test, unpriced no-warn test, chain_for reason).
GREEN: full suite 741 passed; ruff check: All checks passed!; ruff format --check: 82 files already formatted.
