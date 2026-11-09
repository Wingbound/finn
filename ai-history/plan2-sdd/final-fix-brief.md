# Plan 2 final-review fix wave: findings and controller rulings

The final review (opus, dbfa7f7..6c3de47) returned "Ready to merge: with fixes". Fix every item below in one wave. Each item has the reviewer's finding, then the controller's ruling, which binds you. File:line references are the reviewer's, at HEAD 6c3de47.

## C1 (Critical): revised integrated filings are dropped, so the code uses erroneous originals

**Finding:**
- `finn/ingest/xbrl.py:87-95` calls `strptime(raw["broadcast_Date"])`, which raises TypeError on null. The row is skipped as malformed.
- Revised rows have `broadcast_Date: null`, `revised_Date: "31-OCT-2025 23:59:50"` (note the upper-case month) and `revision_Remark`. 14 such rows exist live.
- Dedupe (`:96-98`) never sees the revision, so the erroneous original is used. For CGPOWER and IDFCFIRSTB Sep-2025, the original's OneD context spans 6 months, so YoY is lost. Elsewhere, wrong numbers would be shown silently.
- Knock-on effects:
  - (b) if the newest period's consolidated row exists only as a revision, `_ingest_symbol` (`results.py:305-311`) picks standalone, or an older period;
  - (c) a missing target is skipped silently (`results.py:316-317`).

**Ruling:**
- In `parse_filing_list`:
  - each row's timestamp is `broadcast_Date or revised_Date`; drop a row only if both are missing or unparseable;
  - parse both formats (`07-Nov-2026 17:33:17` and `31-OCT-2025 23:59:50`). `%b` is case-insensitive; verify it.
  - Within each (period_end, basis) group, the row with the **latest** timestamp (revisions included) supplies `xbrl_url`, `format` and `audited`.
  - `filed_at` is the **earliest non-null `broadcast_Date`** in the group, falling back to the revision time only when the group has no broadcast at all. Do NOT use the revision date as `filed_at`: `attach_results` matches cards to stories on `filed_at` within 4 days.
  - Add `revised: bool` to `FinancialsFiling` (True when the chosen row is a revision).
- In `_ingest_symbol`:
  - after parsing, add `if q.period_end != filing.period_end:` record `f"{target} period mismatch: list {filing.period_end}, document {q.period_end}"` and skip the row (`continue`), next to the existing basis check;
  - a target the list does not contain at all must be recorded in `failed` as `f"{target} not on file"`, not skipped silently.

  A stored original heals on the next refresh, because the revised URL is new: it is fetched, and `INSERT OR REPLACE` overwrites the row. Test this.
- Tests:
  - a revised row (broadcast null) supersedes the original: URL from the revision, `filed_at` from the original's broadcast;
  - a revised-only group is kept, with `filed_at` from the revision;
  - the upper-case-month revised date parses;
  - ingest replaces a stored original when the revised URL appears;
  - a period mismatch is skipped and recorded;
  - a missing target is recorded as "not on file".

  Build the revised rows by editing copies of the TATASTEEL list fixture rows in the test.

## I1 (Important): a 429 triggers the outage failover

**Finding:** `router.py:90` gives a non-last model `retries=1`, and `:139-140` treats 429 like 5xx. Groq's 8K TPM is predictable, so back-to-back calls get downgraded to Flash-Lite, whose JSON slipped (`Invalid \escape`) and lost a filing. DESIGN.md promises a "token-bucket per provider", which does not exist.

**Ruling:**
- In `_request`, 429s get their own budget. Honour Retry-After (already clamped to 60 s via `_retry_delay`) for up to `MAX_RETRIES` 429 retries on **every** model, last or not.
- Only 5xx and transport errors use the fast-failover `retries` budget, which stays 1 for non-last models.
- Add one-shot JSON repair in `_parse_json`: on a `json.JSONDecodeError` whose message contains "Invalid \\escape", retry once after `re.sub(r'\\(?![\\/"bfnrtu])', r'\\\\', text)`.
- Tests:
  - Groq answers 429 (Retry-After 7), 429 (Retry-After 7), then 200, with a Gemini key set. Groq answers, Gemini gets 0 calls, and `no_sleep == [7, 7]`.
  - Pin `no_sleep == [1]` in `test_falls_back_to_gemini_on_groq_5xx`.
  - The JSON-repair test turns `{"a": "x\\'y"}`-style invalid-escape text into a dict.
  - A truly invalid JSON still raises `LLMError`.

## I2 (Important): request-time paths can raise on stored data

**Finding:**
- `people.py:150-156` calls `PersonChange.model_validate` unguarded; one bad row makes `build_digest` return a 500.
- `attach_results` (`digest.py:69-70`, into `card_for`, `get_financials`, `QuarterFinancials`, `json.loads`, `fromisoformat`) is also unguarded.

**Ruling:**
- In `attach_people`, catch `ValidationError`, `ValueError`, `KeyError` and `TypeError` per row; log a warning and skip.
- In `attach_results`, catch the same per symbol around `card_for`, log a warning and leave `results=None` ("numbers pending").
- Tests: a corrupt people row and a corrupt financials row (bad `facts_json`) each leave the digest building, with that item absent.

## I3 (Important): DESIGN.md is stale on Plan 2 decisions

**Ruling:** edit `docs/DESIGN.md`:
- (a) `:71` "PyMuPDF … APScheduler" becomes pypdf (BSD; PyMuPDF is AGPL), with no APScheduler: refresh runs out-of-band.
- (b) `:83`: the People-bio routing row becomes "Groq gpt-oss-120b over the filing's own text (Brief Profile), behind a grounding guard; Gemini fallback". `:31`'s "Source 2 … Google Search grounding" is marked "(not built: filing profile only)".
- (c) `:85`: the EBITDA formula becomes "Revenue from operations − (Expenses − finance costs − D&A), i.e. excludes other income; matches screener's Operating Profit".
- (d) `:88`: "token-bucket per provider" becomes "Retry-After-paced backoff on 429 (no failover on rate limits); failover only on outages".
- (e) `:89`: remove "picks the primary model from the results-extraction eval". Results come from XBRL with no model; Gemini's role is the fallback and Plan 3 transcripts.

## FIX-BEFORE-MERGE minors

- **M1, notes:** `results.py:263,269`.
  - indas/nbfc: "PBT includes an exceptional gain of ₹x cr." or "… exceptional loss of ₹|x| cr.", with the sign convention confirmed (positive = gain).
  - Associates: "PAT includes ₹x cr share of profit of associates and joint ventures." or "… a ₹|x| cr share of loss of associates and joint ventures."
  - bank: a neutral "PBT includes exceptional items of −₹x cr" or "₹x cr", with the sign written before the ₹ symbol.
  - The lenders note becomes per-format:
    - bank: "Banks are shown on net interest income and pre-provision profit; EBITDA does not apply."
    - nbfc: "NBFCs are shown on net interest income and credit cost; EBITDA does not apply."
  - Update the existing tests' substring checks accordingly.
  - Add a negative-exceptional test using the TATASTEEL Jun-2026 fixture (exceptional −345.48 gives "exceptional loss of ₹345.48 cr").
  - Add a bank or NBFC exceptional-note test.
- **M2:** in `_usable` (`results.py:175-176`), also require `other.format == cur.format`. Test it.
- **M3, fact words** (`brief.py:109-111`): a digit-bearing fact value must also have every alphabetic word of 3+ characters appear as a word in the source (`phrase_in_text(word, source)`).
  - Excluded unit words: crore, crores, cr, lakh, lakhs, rs, inr, mn, million, bn, billion, per, cent, percent, shares, equity, each, face, value.
  - Test: "Zeta Corp, 100%" is dropped when "100" is in the source but "Zeta" is not; "₹1,250 crore" is kept.
- **M5 (partial):** in `people.py:106-110`, role and effective use `phrase_in_text` (word boundaries) instead of a raw substring. Test: role "MD" against a text containing only "amdocs" gives None.
- **M6:** `refresh._router` (`refresh.py:31-40`) builds the router when **any** provider in `chain_for("classify")`, `chain_for("bio")` or `chain_for("oneliner")` has a key set; it returns None only when none does. Test: Groq key empty, Gemini set, gives a router.
- **M8:** an API-level test showing that the `/digest` JSON serialises `people` and `brief` on stories.

## Docs: EVALS limits (controller ruling from PD3)

Add a short "### Limits of the grounding guard" subsection to `docs/EVALS.md` (§2 or a new §3). The guard proves that names, profile sentences, roles, numbers and quotes **exist** in the filing. It does not prove:
- that a profile belongs to that person when several profiles share a PDF;
- the direction of a change for a real person;
- the units next to a number;
- that a fact's label is correct;
- the one-liner's non-numeric claims.

Keep it plain and honest, 6–8 lines.

## Out of scope (stays deferred; do not do)

M4 (unit-aware numbers), the rest of M5 (name-near-change-term proximity), M7 (caching bad XBRL URLs / exit-code split → Plan 5), and every STAY-DEFERRED ledger item.

## Process

- TDD for each code item.
- At the end, run `cd backend && uv run pytest -q`, then `uv run ruff check . && uv run ruff format --check .`.
- Do NOT run live refresh or live eval.
- Commit in logical commits (for example C1, I1, I2+M-guards, notes/M1-M3, docs), each message ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Write your report to `finn/.superpowers/sdd/2026-11-09-plan2-push-enrichment/final-fix-report.md`, listing per item what changed, the covering tests, and the commands with their output.
