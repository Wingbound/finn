# Task 7b (live-tuning addendum): findings from the first live dossier build

## Why

The live build of PERSISTENT on 2026-11-09 produced a dossier in 237 s with 9 LLM calls ($0.039 at list price). Problems:

1. **All 14 ledger rows were "pending".** The judge said "not discussed in the provided later calls / partial excerpt". The evidence block per later source is `relevant_window(tagged_text(src), terms, 6000)`. With generic terms (revenue, margin, growth…) that window fills with early hits, so the real follow-ups are missing. Example: the "$2 billion aspiration" is surely revisited in later calls.
2. **The "reason" chain starts with `gemini-3.8-flash`,** which failed or hung on the free tier, so every reason call waited for the fallback. The LLM time actually logged was 49 s, so most of the 237 s went on failed 3.8 attempts and downloads.
3. **Guidance extraction kept statements of current fact as promises.** Example: "Persistent today is roughly a $1.654 billion entity from a FY26 perspective."
4. **Bull/bear points citing computed figures were dropped.** The model cited them with `source_id: "FACTS"` (revenue CAGR 26.8%, ROCE 34%, virtually debt-free), and the guard rejects any non-source id. These are legitimate: the numbers come from filed financials and are computed by code.
5. **The progress line "Found 34 transcripts and 15 annual report(s)" misleads,** because only the latest 4 transcripts and the latest AR are read.

## Changes

### A. Judge evidence: full later transcripts (`finn/research/ledger.py`)
- The evidence block for each later source is `tagged_text(src, 90_000)`, the whole transcript, instead of `relevant_window(..., 6000)`. Keep the `=== {id}: {title} ===` headers, in chronological order.
- The prompt adds: "Search all of the later calls; management often revisits a target with new numbers or a new date. Prefer the most recent mention."
- Tests:
  - the judge prompt for a T4 promise contains a sentence taken from a late page (page ≥ 15) of T1 in the fixture, which proves the whole transcript is included;
  - existing ledger tests still pass.

### B. Model routing (`finn/config.py`, `finn/llm/costs.py`)
- `finn_model_reason` default becomes `"gemini-3.5-flash-lite"`. The comment should say why: gemini-3.8-flash was unreliable on the free tier on 2026-11-09 (503s, 45 s hangs).
- `FALLBACKS["reason"] = [("gemini", "gemini-3.1-flash-lite")]`.
- `FALLBACKS["extract_transcript"] = [("gemini", "gemini-3.1-flash-lite")]`. Transcript prompts of about 15–25k tokens exceed Groq's 8K TPM, so Groq can't be the fallback.
- `extract_pdf` is unchanged.
- The "every default model has a list price" test must still pass. `gemini-3.1-flash-lite` is already priced.
- Tests: `chain_for("reason")` and `chain_for("extract_transcript")` equal the new chains.

### C. Forward-looking guidance only (`finn/research/guidance.py`)
- The system prompt adds a rule: "Only forward-looking statements: targets, guidance, plans, expectations, intentions or commitments about the future. Exclude statements of current or past fact (results achieved, the company's current size or margins), even if they contain numbers."
- Tests: the system prompt contains "forward-looking" and "Exclude statements of current or past fact".

### D. Computed facts are citable (`finn/research/synthesis.py`, plus a note in `finn/models.py`'s `Citation` docstring)
- A bull or bear point may cite `source_id: "FACTS"`.
  - Its `quote` must equal (after `grounding.normalize`) one line of the FACTS block, or be a ≥ 3-word substring of exactly one line. The citation stored is `Citation(source_id="FACTS", page=0, quote=<that full FACTS line>)`.
  - Numbers in the point must be grounded in that FACTS line.
- The snapshot never accepts FACTS: there are no facts there, and the snapshot is narrative.
- The bull/bear prompt explains: "cite a transcript or annual report page, or a FACTS line for computed financials (source_id FACTS)".
- Tests:
  - a bull point citing a real FACTS line, with grounded numbers, is kept, with page 0 and the full line as the quote;
  - a FACTS citation whose quote matches no line is dropped;
  - a FACTS-cited point with a number not in that line is dropped;
  - the snapshot rejects FACTS.
- `cite.locate` is unchanged. FACTS handling lives in synthesis.

### E. Honest progress text (`finn/research/pipeline.py`)
- The message becomes `f"Found {n} transcripts (reading the latest {k}) and {m} annual report(s) (reading the latest)"`, where k = min(n, max_transcripts). When m == 0 it ends `"and no annual report"`.
- Update the pipeline test's assertion.

## Constraints

- TDD.
- Run `cd backend && uv run pytest -q`, `uv run ruff check .` and `uv run ruff format --check .`.
- Commit with a message ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No network. Never read `backend/.env`. Do not run live builds.
