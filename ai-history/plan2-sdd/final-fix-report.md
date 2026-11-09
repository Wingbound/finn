# Plan 2 final-review fix wave: report

Branch `feat/push-enrichment`, base 6c3de47. Every item in `final-fix-brief.md` is done, in the order C1, I1, I2, M-items, docs. Each code item was test-first: the new tests were written, seen failing, then made to pass. M8 is the exception: it pins behaviour that already worked, so it passed on first run.

## Commits

| SHA | Subject |
|---|---|
| 7c92224 | fix(ingest): use revised integrated filings; record period mismatch and missing targets |
| d17146b | fix(llm): wait out 429s instead of failing over; repair invalid JSON escapes |
| ddc9afc | fix(digest): skip corrupt stored people and financials rows instead of a 500 |
| 206a806 | fix(results): signed exceptional and associates notes; per-format lender note; same-format comparisons |
| d81dbf9 | fix(enrich): ground a numeric fact's words; word-boundary role and effective |
| d9c9424 | fix(refresh): build the LLM router when any provider on a refresh task's chain has a key |
| a2e6447 | docs: bring DESIGN.md up to Plan 2; add the grounding guard's limits to EVALS.md |

## Per item

### C1: revised integrated filings (7c92224)

**What changed**
- `finn/ingest/xbrl.py`:
  - New `_timestamp()`: it parses `%d-%b-%Y %H:%M:%S` and returns None when the value is null or does not parse. `%b` ignores case: `strptime("31-OCT-2025 23:59:50", ...)` and `"31-oct-..."` both parse, checked by hand and in a test.
  - `parse_filing_list` takes each row's timestamp as `broadcast_Date or revised_Date`. It drops a row only when neither date parses.
  - Rows are grouped by `(period_end, basis)`. The row with the latest timestamp supplies `symbol`, `xbrl_url`, `format` and `audited`.
  - `filed_at` is the earliest non-null broadcast in the group. With no broadcast at all, it is the earliest revision time.
  - `FinancialsFiling.revised: bool = False` is True when the chosen row has a revised date.
- `finn/enrich/results.py::_ingest_symbol`:
  - A missing target now records `f"{target} not on file"`.
  - A document whose `period_end` differs from the list row records `f"{target} period mismatch: list {filing.period_end}, document {q.period_end}"` and is skipped. This check sits next to the basis check.

**Tests**
- `tests/test_xbrl.py`:
  - `test_revision_supersedes_original_but_keeps_its_filed_at`: the URL, audited and format come from the revision, and `filed_at` is the original's 07-Nov 17:33:17.
  - `test_revision_supersedes_original_in_the_full_list`: still 14 filings.
  - `test_revised_only_group_is_kept_with_revision_time`
  - `test_upper_case_month_revised_date_parses`
  - `test_earlier_revision_loses_to_a_later_one`
  - `test_row_without_any_usable_date_is_dropped`
  - `test_unparseable_broadcast_falls_back_to_revised_date`
  - `test_parse_filing_list_dedupes_rebroadcasts` replaces `..._dedupes_revisions`. It now checks that the later row's URL wins while `filed_at` stays the first broadcast; the old assertion contradicted the ruling.
- `tests/test_results_store.py`:
  - `test_revision_replaces_stored_original_on_next_ingest`: this is the healing case. The second ingest fetches only the revised URL and gives `(fetched, skipped) == (1, 2)`. `INSERT OR REPLACE` stores the restated revenue, and `filed_at` stays 07-Nov 17:33:17.
  - `test_revised_only_newest_period_keeps_consolidated`: knock-on (b); consolidated is still chosen.
  - `test_period_mismatch_target_is_skipped_and_recorded`
  - `test_missing_target_is_recorded_not_on_file`

The revised rows are edited copies of TATASTEEL list fixture rows: `broadcast_Date: None`, `revised_Date: "01-DEC-2026 12:00:00"`, `revision_Remark`, `type_Sub: "Revised"` and a new URL.

### I1: 429 is not an outage (d17146b)

**What changed** (`finn/llm/router.py`)
- `_request` keeps two budgets:
  - `rate` covers 429s: `MAX_RETRIES` on every model, paced by `_retry_delay(Retry-After)`.
  - `outage` covers 5xx and transport errors: the `retries` argument, which stays 1 for a non-last model.
- `_parse_json` retries once on a `JSONDecodeError` whose `msg` contains `Invalid \escape`, after `_repair_escapes`.

**Tests** (`tests/test_llm_router.py`)
- `test_rate_limit_waits_on_primary_instead_of_failing_over`: Groq returns 429 (7), 429 (7), then 200, with a Gemini key set. Gemini gets 0 calls and `no_sleep == [7, 7]`.
- `test_rate_limit_budget_is_separate_from_outage_budget`: 429, 503, 429, then 200 stays on Groq, with `[7, 1, 7]`.
- `test_persistent_rate_limit_fails_over_after_its_budget`: 4 Groq calls with `[7, 7, 7]`, then Gemini.
- `test_falls_back_to_gemini_on_groq_5xx` now pins `no_sleep == [1]`.
- `test_invalid_escape_is_repaired_once`: end to end through the router. The input is `{"a": "x\'y", "b": "c:\\d"}`.
- `test_parse_json_repairs_invalid_escape`
- `test_parse_json_still_rejects_truly_invalid_json`: three cases, including repairable escapes in otherwise broken JSON. Each raises `LLMError`.

### I2: request-time paths survive corrupt stored rows (ddc9afc)

**What changed**
- `finn/enrich/people.py::attach_people`:
  - Each stored person is validated inside a try. `ValidationError`, `ValueError`, `KeyError` and `TypeError` log a warning and skip that row.
  - A non-list `people` payload is skipped too.
- `finn/digest.py`: a new `_card_or_none` wraps `card_for` per symbol and catches the same four exceptions. It also rejects a naive `filed_at`, which would otherwise raise `TypeError` in the 4-day comparison outside the guard. On any of these it logs a warning and leaves `results=None`.
- `finn/db.py::get_enrichments` skips a row whose `payload_json` is not a JSON object, with a warning. See Deviations.

**Tests**
- `tests/test_people.py`:
  - `test_corrupt_people_row_is_skipped_not_fatal`: four bad rows next to a good one; only the good one shows.
  - `test_unreadable_people_payload_leaves_digest_building`: four cases (bad JSON, non-list `people`, a non-object payload).
- `tests/test_digest_results.py`: `test_corrupt_financials_row_leaves_digest_building` has six cases:
  - `facts_json` as bad JSON, as a list, or with a non-numeric fact;
  - a bad `format`;
  - a bad `period_start`;
  - a naive `filed_at`.

  Each builds the digest, and the results story has `results is None`.

### I3: DESIGN.md (a2e6447)

- (a) `:71`: pypdf (BSD; PyMuPDF is AGPL), no APScheduler; `scripts/refresh.py` runs out-of-band.
- (b) `:83`: the routing row says "Groq gpt-oss-120b over the filing's own text (Brief Profile), behind a grounding guard; Gemini fallback". `:31`'s Source 2 is marked "(not built: filing profile only)".
- (c) `:85`: the EBITDA formula is "Revenue from operations − (Expenses − finance costs − D&A), i.e. excludes other income; matches screener's Operating Profit".
- (d) `:88`: see Deviations for the wording.
- (e) `:89`: the results-eval clause is removed. In its place: "Results numbers come from XBRL with no model; Gemini's role is the fallback for the Groq tasks and, in Plan 3, transcript extraction."

### M1: notes (206a806)

**Sign convention confirmed from the fixtures:** PBT = ProfitBeforeExceptionalItemsAndTax + ExceptionalItemsBeforeTax.
- TATASTEEL Sep-2026: 4,994.20 + 348.68 = 5,342.88.
- TATASTEEL Jun-2026: 4,086.86 − 345.48 = 3,741.38.

So a positive value is a gain. PAT = PBT − tax + share of associates (5,342.88 − 1,755.56 + 112.27 = 3,699.59).

**Notes as now written**
- indas and nbfc: "PBT includes an exceptional gain/loss of ₹|x| cr."
- bank: "PBT includes exceptional items of −₹x cr." (U+2212 before ₹) or "₹x cr.". The sign convention is not confirmed for banks, so the note stays neutral.
- Associates: "PAT includes ₹x cr share of profit of associates and joint ventures." or "PAT includes a ₹|x| cr share of loss of associates and joint ventures."
- The lender note is now per format, from `_BASIS_NOTES`:
  - bank: "Banks are shown on net interest income and pre-provision profit; EBITDA does not apply."
  - nbfc: "NBFCs are shown on net interest income and credit cost; EBITDA does not apply."

**Tests** (`tests/test_results.py`)
- Updated: `test_tatasteel_q2_card` (exact note strings), `test_bank_card_idfc` (bank note; no exceptional note when the item is 0), `test_nbfc_card_bajaj` (NBFC note).
- New:
  - `test_negative_exceptional_is_a_loss`: the Jun-2026 fixture gives "exceptional loss of ₹345.48 cr".
  - `test_nbfc_exceptional_uses_gain_or_loss`
  - `test_bank_exceptional_note_is_neutral_and_signed`: two cases.
  - `test_negative_associates_share_is_a_loss`

### M2: same format (206a806)

`_usable` also requires `other.format == cur.format`. Test: `test_format_mismatch_is_ignored` gives no QoQ or YoY, and both "No … comparison" notes appear.

### M3: words in numeric facts (d81dbf9)

**What changed** (`finn/enrich/brief.py`): a new `_fact_words_grounded`. It applies to a fact value that contains a digit.
- The value is normalised and split into `\w+` tokens.
- Each purely alphabetic token of 3+ letters that is not in `UNIT_WORDS` must pass `phrase_in_text(word, source)`.
- `UNIT_WORDS` is the brief's list of 19 words.
- Mixed tokens such as an ISIN are not alphabetic words, so they are skipped.

**Tests** (`tests/test_brief.py`)
- `test_numeric_fact_words_must_be_in_source`: "Zeta Corp, 100%" is dropped; "₹1,250 crore" and "100% of Alpha Ltd" are kept.
- `test_numeric_fact_unit_words_need_not_be_in_source`
- `test_numeric_fact_word_matched_on_word_boundaries`: "6 mon" is dropped against "months"; the ISIN is kept.

### M5 (partial): role and effective (d81dbf9)

`_grounded_or_none` uses `phrase_in_text`. Test: `test_role_and_effective_match_whole_words_only`. Against a text containing "Amdocs" and "1st June", role "MD" gives None and effective "1st Jun" gives None. Whole phrases are kept.

### M6: router construction (d9c9424)

`refresh._router` builds the router when any provider on `chain_for("classify" | "bio" | "oneliner")` has a key. The note names every missing key.

**Tests** (`tests/test_refresh.py`)
- `test_router_built_when_only_a_fallback_provider_has_a_key`: Groq empty and Gemini set gives an `LLMRouter`; the reverse does too.
- `test_router_none_when_no_provider_has_a_key_or_llm_is_off`
- The existing `test_use_llm_without_keys_degrades_to_rules` still passes, because the note contains GROQ_API_KEY.

### M8: API serialisation (d9c9424)

`tests/test_api.py::test_digest_story_serialises_people_and_brief`:
- It seeds a VOLTAS management_change filing with a stored person and a TRENT mna filing with a stored brief.
- It POSTs `/digest` and asserts the exact `people` and `brief` JSON on each story, with `[]` and `null` on the other.

### Docs: EVALS limits (a2e6447)

`docs/EVALS.md` gets a new "## 3. People and briefs / ### Limits of the grounding guard" section: 7 lines covering the five non-guarantees in the ruling.

## Deviations

1. **JSON repair regex.** I used a pair-consuming substitution, `re.sub(r"\\(.)", …)`, which keeps `\\`, `\/`, `\"`, `\b`, `\f`, `\n`, `\r`, `\t` and `\u` and doubles any other backslash. The ruling's lookahead regex, `\\(?![\\/"bfnrtu])`, looks at the second backslash of a valid `\\` pair on its own. In `"c:\\d"` it would double that backslash and corrupt a valid escape whenever another invalid escape in the same reply triggers the repair. The intent (one-shot repair of invalid escapes) is unchanged. `test_invalid_escape_is_repaired_once` covers the difference.
2. **`get_enrichments` hardening.** A non-JSON `payload_json` raised inside `db.get_enrichments`, before `attach_people`'s per-row guard could run. That would fail every story, and briefs too. It now skips such rows with a warning. This is the smallest change that makes "a corrupt people row leaves the digest building" hold for unreadable rows as well as schema-invalid ones.
3. **Naive `filed_at` in `attach_results`.** The ruling guards around `card_for`. A stored `filed_at` without an offset parses fine but raises `TypeError` in the 4-day comparison that follows. `_card_or_none` therefore treats a naive `filed_at` as corrupt as well.
4. **DESIGN.md (d) wording.** I kept the ruling's sentence but wrote "no *early* failover on rate limits; *fast* failover only on outages", and added: "Each model waits out up to 3 rate limits (Retry-After, capped at 60 s) before the chain moves on; a 5xx or transport error moves on after 1 retry when a fallback is behind it." The code, per the I1 ruling, still moves to the next model once a model's own 429 budget is spent. The verbatim "no failover on rate limits" would have overstated that.
5. **Revision-only groups with several revisions** take the earliest revision time as `filed_at`. The ruling says "the revision time" and does not cover several. The earliest is closest to the results story that `attach_results` matches against.

## Concerns

- **"not on file" sets the exit code.** It now lands in `refresh` `errors`, so a symbol with no year-ago or prior quarter makes `refresh.py` exit 1. A recent listing would do this. That matches the ruling; the warning/error exit-code split is M7, deferred to Plan 5.
- **`/results/{symbol}` is unguarded.** It still calls `card_for` without the I2 guard, so a corrupt financials row returns a 500 there. This was not in the ruling's scope; a one-line reuse of `_card_or_none` would close it.
- **The stored seed still holds unrevised originals.** It was not touched (as instructed), so for CGPOWER and IDFCFIRSTB Sep-2025 it keeps the originals until the next live refresh. The healing path is tested offline only.

## Commands and output

```
$ cd backend && uv run pytest -q
........................................................................ [ 19%]
........................................................................ [ 39%]
........................................................................ [ 58%]
........................................................................ [ 78%]
........................................................................ [ 97%]
........                                                                 [100%]
368 passed in 2.25s

$ uv run ruff check . && uv run ruff format --check .
All checks passed!
62 files already formatted
```

That is 325 tests at 6c3de47 and 368 now (+43). No network was used in tests. No live `refresh.py` or `eval_results.py` was run, and `backend/.env` and `backend/seed/` were not touched.
