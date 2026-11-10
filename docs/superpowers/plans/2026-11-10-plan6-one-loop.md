# FINN Plan 6: One Loop (results meet promises)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push and Pull become one loop, as `docs/DESIGN.md` §1 promises.
- A results story in Today shows what management said on its calls, beside the filed numbers.
- A dossier shows the company's latest filed quarter.

**Architecture:** `finn/research/link.py` selects a company's open promises from its stored dossier for a given results card. It adds a deterministic pace note only under strict gates. `build_digest` attaches the notes to results stories, and `/research/{sym}` adds the latest card. The frontend renders both. Dossiers are built for the 16 portfolio companies that lack one, so the loop shows on Today.

**Spec:** `docs/DESIGN.md` §1 ("Results card … plus a 'vs promise' chip from the Promise Ledger") and §8.

## Global Constraints

- **No verdicts from one quarter.** A pace note compares one quarter with a target and never grades the promise. The ledger alone grades, and only on later-call evidence.
- **Pace gates.** A pace note appears only when all of these hold:
  - the unit is `%` and the target is numeric;
  - the quote itself names the results line:
    - revenue: `revenue`, `sales` or `top line`, together with `grow`/`growth`;
    - PAT: `PAT`, `net profit`, `profit after tax` or `bottom line`;
    - EBITDA margin: `EBITDA margin` or `operating margin`, and never EBIT;
  - `promise.metric` agrees with that line (`revenue_growth`, `pat_growth`, `ebitda_margin`);
  - the horizon resolves through `parse_horizon` to the card's fiscal year or quarter;
  - the quote has no mismatch cue (the ledger's `_MISMATCH`) and no segment cue (`_SEGMENT`);
  - the card has that line (revenue or PAT `yoy_pct`, or the `ebitda_margin` value).
- **Pace wording.** The pace word is `above`, `within` or `below` the target range. With no upper bound, it is `at or above` or `below`.
- **Copy.** Plan 4's provenance rule holds: quotes are set in Literata, FINN's words in Plex. The words "kept" and "missed" never appear in a pace note.

## Review Focus

1. A results story for a company with no dossier renders exactly as before, with no empty panel.
2. A dossier whose promises are all long-horizon or resolved shows at most the open ones, or nothing. It never shows resolved promises as open.
3. A lender's card has no EBITDA line, so EBITDA-margin promises get no pace note.
4. A promise in % whose quote names AUM or PRASK gets no pace note, even when its `metric` field says `revenue_growth`.
5. `/research/{sym}` for a symbol with no results card returns `latest_results: null`, and the dossier page doesn't break.

### Task 1: `link.py` and the digest attachment

- **Models.** `PromiseNote{topic, quote, citation, call, made_in, horizon, target, pace}` and `PaceNote{line, actual, basis, target_low, target_high, word}` in `finn/models.py`. `Story.promises: list[PromiseNote] = []`.
- **`promise_notes(d, card, limit=3)`.**
  - Selection: only pending rows. Rows whose horizon resolves to the card's FY or quarter come first, then quantitative rows, then the newest call. Long-horizon rows ("long term", or an FY two or more years past the card's) come last.
- **`attach_promises(conn, stories)`.** Runs for results stories, with one dossier lookup per symbol per call. A missing or corrupt dossier gives no notes.
- **Tests:**
  - a pace note fires on a quote naming revenue growth for the card's FY;
  - no pace note fires for AUM, PRASK, EBIT, a segment, a long horizon, or a lender's EBITDA margin;
  - the selection order;
  - a story with no dossier is unchanged;
  - the digest response carries `promises`.

### Task 2: API and frontend

- **API.** `/research/{sym}` adds `latest_results: ResultsCard | null`, using `card_or_none`.
- **Frontend.**
  - A `PromisePanel` sits under the `ResultsGrid` on results stories: "What management said". Each note shows the quote (Literata, 3-line clamp), "{call}, target {target}, {horizon}", and the pace line when there is one: "This quarter: revenue +21.6% YoY, above the 15–18% range. One quarter, not the year." It ends with a "See the ledger" link.
  - The dossier gets a "Latest filed quarter" section using `ResultsGrid`.
- **Tests:**
  - the panel renders the notes and the pace;
  - nothing renders without notes;
  - the dossier renders with and without `latest_results`;
  - fixtures are re-exported and `types.test.ts` is extended.

### Task 3: Data, docs, polish

- **Data.** Build dossiers for the 16 portfolio companies without one and merge them into the latest snapshot. Re-export the fixtures. Record each build's time and cost in EVALS.
- **Polish (deferred minors that users see):**
  - "1 promises tracked";
  - citation chips at 44 px;
  - plain-language build errors ("build timed out" becomes "The build ran out of time on the server. Try again; the data FINN read is cached").
- **Docs.** Update the README and DESIGN; take screenshots.
