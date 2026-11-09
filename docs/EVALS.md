# FINN evals

## 1. Filing classification

`backend/scripts/eval_classify.py` scores the classifier against a labelled gold set,
`backend/tests/fixtures/gold/classification.jsonl`.

**This eval is in-sample.** The rules were tuned on
`backend/tests/fixtures/nse/portfolio_month.json`, and the gold set is sampled from that same
file. The numbers below show how well the rules fit the month they were written against.
They are not an estimate of accuracy on filings the rules have never seen, which will be
lower. An out-of-sample check needs a gold set drawn from a later month.

### Gold set

- **Source:** `backend/tests/fixtures/nse/portfolio_month.json`, 323 real NSE announcements
  for the 18 portfolio symbols, 8 Oct to 8 Nov 2026.
- **Sample:** 104 rows. The sample is stratified by NSE `desc`: for each desc in sorted order,
  the rows are sorted by `seq_id` and `random.Random(20261108)` draws ceil(25%) of them, with a
  minimum of 1. All 45 descs present appear at least once. 48 rows come from the descs the
  rules treat as ambiguous (Outcome of Board Meeting, Analysts/Institutional Investor Meet,
  Press Release, General Updates, Updates, Shareholders meeting, Committee Meeting Updates,
  Monthly Business Updates). This code reproduces the sample exactly, in order, when run
  from `backend/`:

  ```python
  import json, math, random
  from collections import defaultdict

  rows = json.load(open("tests/fixtures/nse/portfolio_month.json"))
  groups = defaultdict(list)
  for r in rows:
      groups[r["desc"]].append(r)
  rng = random.Random(20261108)
  sample = []
  for desc in sorted(groups):
      items = sorted(groups[desc], key=lambda r: int(r["seq_id"]))
      sample += rng.sample(items, max(1, math.ceil(0.25 * len(items))))
  ```

- **Labels were written by an AI assistant (Claude), not by a person.** Each row was labelled
  from its NSE desc, subject and NSE summary against the taxonomy in
  [PROJECT_BRIEF.md §5](PROJECT_BRIEF.md). The labels were finished before the classifier was
  run on these rows and have not been changed since (file sha256 `b3b0a26a…802d549` at the
  time of the run below). 36 rows were judgment calls, and each of those carries a `notes`
  field explaining the decision.
- **Pending: the author will spot-check 20 rows by hand.** The rows with `notes` are the best
  place to start.
- **Labelling conventions:**
  - `noise: true` (category `unclassified`) marks pure paperwork: newspaper copies,
    depository certificates and share-certificate notices. Newspaper ads of results are
    labelled noise too, even though the reference taxonomy lists them under results, because
    the results filing itself carries the signal. Each of those rows has a note saying so.
  - The IPO of a subsidiary is labelled `mna`, since it dilutes or sells the parent's stake,
    and not `fund_raise`.
  - A filing whose subject has no content (for example "Outcome of Committee Meeting") is
    labelled from whatever context exists. Without any, it is labelled `unclassified`.
- **Mix:** unclassified 18, results 15, management_change 11, press_release 10, mna 9,
  earnings_call 9, noise 9, investor_meetings 5, credit_rating 4, litigation 3, fund_raise 3,
  dividend 2, postal_ballot 2, agm_egm 2, bonus_split 1, capex 1. The month has no
  insider_trading or pledging filings.

### Metrics

- **Overall accuracy:** the predicted category matches the gold category. For a gold noise
  row, the prediction matches when it has `noise=True`.
- **Material-category accuracy:** the same, restricted to rows whose gold category has a base
  score of 45 or more (results, mna, management_change, pledging, litigation, credit_rating,
  fund_raise, capex, insider_trading). That is 46 rows.
- **Rules coverage:** the share of rows where `classify_rules` returned a classification
  instead of None.
- **Rules precision:** of the rows the rules labelled, the share they labelled correctly.
- **Default matches:** correct rows that were rule misses, where the fallback
  `unclassified` happened to equal the gold label. They count toward overall accuracy
  without any classifier having recognised them.
- **Misses:** each miss is listed as seq_id · gold → predicted · subject[:80].

### Results

| mode | overall accuracy | material-category accuracy | rules coverage | rules precision |
|---|---|---|---|---|
| Rules only (`--no-llm`), 2026-11-08 | 85.6% (89/104) | 84.8% (39/46) | 80.8% (84/104) | 92.9% (78/84) |
| Rules + LLM (`groq/openai/gpt-oss-120b`, reasoning effort medium), 2026-11-09 | **91.3% (95/104)** | 87.0% (40/46), below the 90% target | 80.8% (same rules) | 92.9% (same rules) |

Two caveats on the rules-only row, both printed by the script:

- **Rules precision is 78/84 = 92.9%.** On the rows the rules chose to label, they were wrong
  6 times.
- **11 of the 89 correct rows are default `unclassified` matches.** The rules returned None
  for those rows and the fallback label happened to be right. Without them, the rules
  themselves got 78 of 104 rows right (75.0%).

Rules-only misses (15). A row predicted `unclassified` here is a rule miss that took the
default; in LLM mode, those rows go to the LLM.

- 106821438 · mna → press_release · share-swap buyout of a subsidiary's minority stake (NSE desc "Agreements")
- 106819108 · earnings_call → investor_meetings · M&M "Schedule of Analyst Meet Q2F27"
- 106831152 · mna → results · Jio Platforms listing, plus JPL's results intimation
- 106817653 · mna → fund_raise · Jio Platforms IPO, RHP filed
- 106852258 · litigation → unclassified · High Court stays a pollution-board closure order (CG Power)
- 106819825 · noise → unclassified · newspaper ad about lost share certificates (desc "General Updates")
- 106832075 · results → unclassified · "Outcome of Board Meeting held on October 28" (TVS results day)
- 106826784 · press_release → unclassified · untitled press release
- 106851457 · press_release → unclassified · press release titled "Press Release"
- 106841670 · press_release → unclassified · TVS models at EICMA 2026
- 106821846 · results → unclassified · press release filed with the same-day results (UltraTech)
- 106822793 · press_release → unclassified · untitled press release
- 106813301 · unclassified → mna · liquidation of a step-down subsidiary (desc "Sale or disposal")
- 106823997 · press_release → unclassified · "media statement issued by the Company"
- 106852048 · mna → fund_raise · IPO (DRHP) of a material subsidiary (Amber / IL JIN)

**What the LLM can and cannot fix.** Of the 7 material misses, 3 are rule misses that the LLM
will see (106852258, 106832075, 106821846). The other 4 are confident rule hits, and the LLM
never sees those because rules take precedence: two subsidiary IPOs labelled fund_raise,
the Jio listing labelled results, and the share swap labelled press_release. So LLM-assisted
material accuracy can reach at most 42/46 = 91.3%, and a single LLM error on those 3 rows
puts it at 89.1%, below the target. Two smaller points: the LLM prompt cannot return
`noise`, so 106819825 stays a miss in either mode; and the four untitled press releases are
not material.

**What it did fix (2026-11-09).** The LLM got the CG Power High Court stay (106852258) right
and missed the other two: the contentless "Outcome of Board Meeting" (106832075 →
unclassified) and UltraTech's same-day results press release (106821846 → press_release). So
material accuracy is 40/46 = 87.0%, short of the 90% target. The cheapest way to the target
is not a bigger model. It is fixing the four confident rule hits, since the LLM never sees
them. That work belongs with an out-of-sample gold month, so the rules aren't tuned to this
one again.

### Choosing the Groq model (2026-11-09)

Groq has retired its Llama models; its list-models endpoint now offers `openai/gpt-oss-20b`,
`openai/gpt-oss-120b` and `qwen/qwen3.8-27b`. Both gpt-oss models are reasoning models, so
the reasoning effort changes both accuracy and token use. Every run below sends the same 20
rule misses to the LLM in one batch, with a fresh response cache.

| Groq model, reasoning effort | overall | material | output tokens per batch | list price per batch |
|---|---|---|---|---|
| gpt-oss-20b, Groq's default | 85.6% (89/104) | 87.0% | 2,048 | $0.00074 |
| gpt-oss-120b, Groq's default | 91.3% (95/104) | 87.0% | 1,174 | $0.00095 |
| gpt-oss-120b, low | 89.4% (93/104) | 87.0% | 678 | $0.00065 |
| **gpt-oss-120b, medium (chosen)** | **91.3% (95/104)** | 87.0% | 1,304 | $0.00103 |

- Prices are Groq's list prices; FINN runs on the free plan, so nothing is paid.
- Output tokens include reasoning tokens. A direct probe on the same batch found no
  truncation at any setting (`finish_reason=stop`, 20 of 20 items returned).
- The two rows that low effort lost are routine ESG and "General Updates" notices labelled
  press_release. They score below the Important floor either way, but at about $0.0004 more
  per batch, accuracy decides.
- The chosen setting scored 95/104 in all three runs: Groq's default effort, explicit
  medium, and medium after the prompt fix below. Single runs of the other settings may
  vary by a row or two.

**Prompt fix found by the live refresh.** The first LLM-classified snapshot labelled Bajaj
Finance's half-yearly report (PAT +28%) and Voltas's results press release as
`results/intimation`. That subtype scores ×0.3, so both dropped from 90 to 27 and fell into
the routine drawer. Every NSE filing says the company "has informed (intimated) the
Exchange", so the bare label misled the model. The prompt now defines the subtype as a
board-meeting date with no figures (`SUBTYPE_HINTS` in `finn/classify/llm.py`). Both filings
now score 90, and the eval is unchanged at 95/104.

### Live snapshot

The 30-day seed `backend/seed/finn.sqlite` was built on 2026-11-08 with
`scripts/refresh.py --days 30 --no-llm`. Rules classified 253 of its 317 filings (79.8%), and
the other 64 took the `unclassified` default.

On 2026-11-09, `scripts/refresh.py --days 30` with API keys sent those 64 to the LLM:

- **Calls:** 4 batches; 5,875 input and 4,023 output tokens.
- **Cost:** $0.0033 at list price, $0 actually paid on the free plan.
- **Result:** 0 rows left on the default.
- **Labels:** unclassified 44, press_release 16, results 3, litigation 1.
- **What surfaced:** over the same windows (clock pinned to 2026-11-09 09:00 IST), the
  digest shows 9 → 11 stories at 72 hours and 23 → 25 at 7 days. The two new stories had
  been sitting in the routine drawer. One is CG Power's High Court stay of a plant-closure
  order (litigation, Critical). The other is Bajaj Finance's half-yearly results.
- The 24-hour window is empty on a Monday morning, because the last filing was Saturday
  16:58. The frontend's empty state uses `latest_filing_at` for this.

Every refresh re-runs the rules on `by=default` rows, so rule improvements reach them. A run
with an API key also sends the rows the rules still miss to the LLM.

## 2. Results numbers

`backend/scripts/eval_results.py` checks the numbers we derive from NSE XBRL against the
quarterly table on screener.in. screener is a cross-check only; it never feeds the product.

**Method.** For each portfolio symbol it takes the latest stored results card, finds
screener's column for the same month ("Sep 2026"), and compares the pairs below. A pair is
compared only when the screener page's basis (consolidated or standalone) equals the card's
basis. A pair matches when it is within 1% relative or INR 1 crore absolute, whichever is
more lenient. The script reports a table, per-metric match rates and the misses, and always
exits 0.

| format | our value | screener row |
|---|---|---|
| indas | revenue | Sales |
| indas | EBITDA (revenue minus expenses plus finance cost and depreciation) | Operating Profit |
| indas | PBT plus share of associates and JVs | Profit before tax |
| indas | PAT | Net Profit |
| bank | interest earned | Revenue |
| bank, nbfc | PBT | Profit before tax |
| bank, nbfc | PAT | Net Profit |
| nbfc | revenue | Revenue |

The indas PBT comparison adds the share of associates and JVs because screener's "Profit
before tax" includes it and XBRL's ProfitBeforeTax does not.

### Offline result

`uv run python scripts/eval_results.py --offline` uses the recorded screener pages (all
consolidated) and the XBRL fixtures. IDFCFIRSTB and BAJFINANCE file standalone, so they are
skipped rather than compared against the wrong basis. Only TATASTEEL is compared:

| symbol | basis | metric | ours | screener | diff % | match |
|---|---|---|---|---|---|---|
| TATASTEEL | consolidated | revenue | 65,436.24 | 65,436.00 | 0.00 | yes |
| TATASTEEL | consolidated | ebitda | 10,533.07 | 10,533.00 | 0.00 | yes |
| TATASTEEL | consolidated | pbt+assoc | 5,455.15 | 5,455.00 | 0.00 | yes |
| TATASTEEL | consolidated | pat | 3,699.59 | 3,700.00 | -0.01 | yes |
| IDFCFIRSTB | standalone | - | | | | skipped: basis mismatch |
| BAJFINANCE | standalone | - | | | | skipped: basis mismatch |

Match rate: 4/4 on the compared pairs. That is one symbol, so it says the method works, not
how accurate the extraction is across the portfolio.

### Live result (2026-11-09)

`uv run python scripts/eval_results.py --db <refreshed snapshot>` compared all 18 portfolio
symbols. Each symbol's latest card is Q2 FY27 (Sep 2026), except AMBER, whose Sep 2026
integrated filing was not posted yet, so its Q1 FY27 card was compared. Every card was
consolidated, matching screener's consolidated pages.

| metric | pairs | matched |
|---|---|---|
| revenue (indas and NBFC) | 17 | 17 |
| interest earned (bank) | 1 | 1 |
| EBITDA (indas) | 16 | 14 |
| PBT + associates (indas) | 16 | 16 |
| PBT (bank, NBFC) | 2 | 2 |
| PAT | 18 | 18 |
| **all** | **70** | **68 (97.1%)** |

**Both misses are a definition difference.** They are not extraction errors:

| symbol | our EBITDA | screener "Operating Profit" | share of JV/associate result | ours + share |
|---|---|---|---|---|
| VOLTAS | 127.86 | 87 | −41.10 | 86.76 |
| TRENT | 1,078.09 | 1,057 | −21.06 | 1,057.03 |

- Screener nets a negative share of joint-venture results into expenses. For TATASTEEL, whose
  share was positive (+112.27), screener's Operating Profit equals ours exactly.
- FINN's EBITDA excludes equity-accounted JV and associate results, the usual definition of
  operating profit.
- The results card states the JV loss in its notes ("PAT includes a ₹41.10 cr share of loss
  of associates and joint ventures"), so the reader sees it either way.

With that convention accounted for, all 70 pairs agree within 1% or ₹1 cr.

**The run also checked the revised-filing fix.** On the first live refresh, CGPOWER and
IDFCFIRSTB lost their year-ago comparison. NSE had replaced their Sep 2025 filings with
revisions (`broadcast_Date` null, `revised_Date` set), and the parser dropped those rows and
fell back to the erroneous originals, whose "quarter" context spans six months. After the
fix, both symbols carry all three quarters.

## 3. People and briefs

### Live run (2026-11-09, 30-day backfill)

Counts only. These outputs are not hand-checked against a labelled set.

- **People.** 30 management-change filings: 25 yielded people, and 5 had no extractable text
  (scanned or empty), recorded as "no text".
  - 66 people kept after grounding. Every one has a role found in the filing.
  - 24 carry a profile copied verbatim from the filing's Brief Profile.
  - The rest are retirements, resignations, or appointments whose filing omits a profile.
    The card shows less in those cases rather than inventing a bio.
- **Briefs.** 41 eligible filings: 40 got an LLM brief that passed number grounding, and 1 had
  no text and no NSE summary.
  - Briefs carry 116 grounded key facts in total.
  - 37 carry a verbatim supporting quote of 4 or more words.
- **Cost and limits.** The backfill used about 167k tokens.
  - It exhausted Groq's free daily cap of 200k tokens for gpt-oss-120b, including the eval runs
    the same day.
  - Groq answered 37 enrichment calls and Gemini 3.5 Flash-Lite answered 28 after the router
    failed over.
  - Total cost was $0.06 at list price, and $0 actually paid.
  - A daily incremental refresh needs a handful of calls, well inside the free caps.

### Limits of the grounding guard

The guard proves that names, profile sentences, roles, effective dates, numbers and quotes
exist in the filing. It does not prove:

- that a profile belongs to that person when several profiles share one PDF;
- the direction of a change (appointed or resigned) for a person the filing does name;
- the units next to a number ("₹1,250 crore" passes wherever "1,250" appears);
- that a fact's label is right for its value;
- the one-liner's claims that carry no number.

## 4. Research dossiers

`scripts/eval_research.py [--db PATH]` reads every stored dossier (default `DB_PATH`) and prints one Markdown row per dossier plus a totals row. Offline; no LLM calls.

Method:

- **Citation re-verification.** Every citation (ledger promise and evidence, snapshot, bull, bear) is re-located with `cite.locate` in the stored source pages. It must be verbatim, 6+ words, negation-guarded, and land on the stored page. A `FACTS` citation must equal a line of `facts_block` recomputed from the stored dossier; the FACTS citations column counts them. Each failure is listed as `symbol | field | source_id p{page} | quote[:80]`. The figure is 100% *by construction*: the eval re-runs the same matcher that admitted each citation at build time. A failure therefore means stored data changed, or the matcher changed after the build. It does not measure whether the citations are fair.
- **Guard drop rate.** `build_dossier` records `guard` (promises and points proposed vs kept). Drop rate = 1 − kept/proposed, shown for promises and for points. The promise drop rate counts every filter after the model reply, not only quotes that failed verification: the forward-looking cue filter, the conditional filter, de-duplication of repeated quotes, and the cap of 8 promises per transcript.
- **Ledger distribution.** Counts per status, and computed vs judged rows.
- **Cost and latency.** LLM calls, `usd_list_price` and `build_seconds` from the dossier.
- **Live-build budget.** 4 transcripts and 40 AR pages. About 9 LLM calls by design (4 extractions, at most 3 judge calls, 2 synthesis calls), with no enforced cap. A 240 s soft deadline, with no new stage started under 60 s before it. The cost and seconds columns show whether builds stay inside it.
- **Hand audit of resolved rows.** The real fairness measure is a hand audit of the resolved ledger rows (kept, partly, missed). For each row: does the evidence quote show the outcome for the same metric and period, and does the status follow from it? Results are below.

### Live results (2026-11-09, the committed snapshot)

There are 7 dossiers: the 4 demo companies (PERSISTENT, DIXON, POLYCAB, INDIGO) and 3 generalisation checks (HDFCBANK, a bank; BAJFINANCE, an NBFC; IDEA, negative net worth). All were built live from screener, the transcripts and the latest annual report.

| Symbol | Citations verified | FACTS citations | Ledger (kept/partly/missed/pending/dropped) | Promise drop | Point drop | LLM calls | USD (list) | Seconds |
|---|---|---|---|---|---|---|---|---|
| BAJFINANCE | 25/25 | 4 | 0/0/0/19/0 | 27% | 0% | 9 | 0.061 | 84 |
| DIXON | 23/23 | 4 | 0/0/0/16/0 | 50% | 22% | 9 | 0.071 | 97 |
| HDFCBANK | 13/13 | 2 | 2/0/0/5/0 | 56% | 50% | 9 | 0.059 | 99 |
| IDEA | 17/17 | 4 | 0/0/0/11/0 | 21% | 14% | 9 | 0.051 | 82 |
| INDIGO | 22/22 | 3 | 3/0/0/8/1 | 33% | 12% | 9 | 0.054 | 81 |
| PERSISTENT | 22/22 | 4 | 2/0/1/8/1 | 25% | 22% | 9 | 0.033 | 93 |
| POLYCAB | 21/21 | 1 | 0/0/0/17/0 | 29% | 56% | 9 | 0.061 | 82 |
| total | 143/143 | 22 | 7/0/1/84/2 | 36% | 27% | 63 | 0.39 | 618 |

The cost and seconds columns come from the first live build. The verdict guards (below) were then applied by rebuilding from the LLM cache. Those rebuilds made 3 new synthesis calls, because the ledger tally in the prompt changed, and cost $0.017 in all.

- **Cost.** The USD figures understate the real cost a little. The judge and synthesis model, Gemini 3.5 Flash, has no published list price, so its calls are counted but priced at $0 (`UNPRICED_MODELS`). The priced part is the 4 extraction calls per dossier on 3.5 Flash-Lite. Every call ran on the free tier, so the actual spend was $0.
- **Time.** Every build finished in 81–99 s, well inside the 240 s soft deadline and Vercel's 300 s limit.
- **Computed grades: 0 of 94 rows.** The computed path fires only when the quote names the metric and the period, and none of these quotes did. Everything was judged.

**Hand audit, before the verdict guards (11 resolved rows).**
- **Correct: 5.**
  - INDIGO's Q1 FY27 capacity, 3–4% guided and 3% delivered (kept);
  - PERSISTENT's FY26 tax rate, 20–24% guided and 22.6% delivered (kept);
  - PERSISTENT's growth streak (kept);
  - PERSISTENT's shareholder approval, promised at the July AGM and obtained at an October EGM (missed);
  - HDFCBANK's interim chairman serving the stated 3 months (kept, trivial).
- **Debatable: 3.**
  - HDFCBANK's MD announcement: kept, but the rationale names a person the quote does not;
  - INDIGO's Middle East recovery: kept on "90, 95 percentage" against "full capacity", where partly is fairer;
  - INDIGO's flattish Q2 capacity: kept on weak evidence.
- **Wrong: 3, all mechanical.**
  - DIXON's Noida plant was judged kept on a later call that restated the target ("we expect the operation to commence by Q2").
  - IDEA's H1 capex was judged kept at Rs 42 billion against a Rs 50–60 billion target.
  - INDIGO's Q4 FY26 capacity target was graded missed on evidence about the June quarter (Q1 FY27).

  The 2 dropped rows (an investor day, a groundings forecast) are absences, which no quote can verify.

**Verdict guards (Task 7g).** Three deterministic checks run after the judge and can only downgrade a verdict to pending:
- the evidence names a different period than the target;
- the evidence restates the target in the future tense with no delivery wording;
- a quantitative "kept" whose evidence figures all sit below the target.

On this snapshot they fired 6 times: 1 period, 3 restated and 2 below target. Three of the six were the three wrong rows above. The other three were "kept" verdicts that the not-yet-due rule would have made pending anyway. No correct verdict was lost. After the guards there are 8 resolved rows: 5 correct, 3 debatable, 0 wrong.

**Why most rows are pending (84 of 94).**

| Count | Reason |
|---|---|
| 26 | The promise comes from the newest call, so no later call exists to judge it against. |
| 35 | Later calls hold no evidence of the outcome. These are mostly FY27 or longer targets. |
| 9 | A "kept" became pending because the target falls after the newest call ("tracking is not delivery"). |
| 8 | The judge's evidence quote failed verbatim verification. |
| 6 | Held by a verdict guard: 1 period, 3 restated, 2 below target. |

The UI therefore separates "Open promises (latest call)" from "Track record (earlier calls)".

**Run-to-run variance.** Extraction and judging are not deterministic: Gemini 3.x is run at its default temperature, as Google recommends. The judge A/B earlier the same day, on the same transcripts, found POLYCAB's EHV plant slip (end-CY2026 to FY2028) as a miss. This build did not extract the original EHV promise, only the newer FY2028 restatement (pending). The committed snapshot is one run; a rebuild can surface different promises.

**Judge model A/B** (2026-11-09; POLYCAB, DIXON, INDIGO):
- `reason` on 3.5 Flash-Lite found 0 misses; it labelled POLYCAB's EHV slip pending.
- 3.5 Flash found 3 misses, at 72–80 s per dossier: POLYCAB EHV; DIXON Noida, Q2 to Q3 FY27; and INDIGO Q4 FY26 capacity, 10% to 3%. It also found 1 correct kept.
- On re-audit, the INDIGO miss rested on June-quarter evidence, which is the period error the guard now catches.
- 3.8 Flash was still returning 503s or timing out, so `reason` defaults to 3.5 Flash.

### Limits

The judge's status is an LLM judgement gated by verbatim evidence. The quote is checked, and three deterministic guards (period, restatement, figure below target) can only downgrade the verdict; beyond those, the verdict itself is not checked. Computed grades cover only revenue growth, margin and PAT growth, and only when the quote itself names the metric and the period (see DESIGN.md, Ledger grading). Reaffirmations are treated as pending, not as delivery. Citation verification proves a quote exists on its page, not that the claim built on it is right.

## 5. Deployed (2026-11-10)

The frontend is at https://finn-qx98.vercel.app and the API at https://finn-peach.vercel.app. Both are Vercel Hobby projects that deploy from `main`.

- **Seeding.** `/health` reports `seeded: true`: the first request copied the committed snapshot into `/tmp`.
- **CORS.** The only allowed origin is the frontend. A preflight from any other origin gets a 400.
- **Warm API latency.** Every endpoint answered in 0.3 to 0.8 s:

  | Endpoint | Time | Payload |
  |---|---|---|
  | `/portfolio` | 0.58 s | |
  | `/digest`, 24 h | 0.59 s | |
  | `/digest`, 7 days | 0.76 s | 139 KB |
  | `/alerts` | 0.35 s | |
  | `/research` | 0.38 s | |
  | a dossier | 0.35 s | |
  | `/results/M&M` | 0.34 s | |
  | screener search | 1.05 s | |

- **Live builds of companies not in the snapshot:**

  | Company | Route | Time | Outcome |
  |---|---|---|---|
  | ASIANPAINT | API | about 75 s | Finished and saved. A curl client on HTTP/2 lost the stream before `done`, and a retry within 10 minutes got the cached dossier in 0.37 s. |
  | TITAN | API | 75 s | Streamed live over HTTP/1.1, with keep-alive pings every 15 s and a clean close. |
  | PIDILITIND | the UI, Chromium at 390 px | 83 s | The dossier rendered. |

  Each build made about 9 model calls.
- **Live checks.** `playwright.live.config.ts` passes against the deployed site:
  - the tabs load with data;
  - there are no console errors;
  - nothing overflows at 390 px;
  - a citation opens with its quote highlighted.

- **Scheduled refresh from GitHub Actions** (run 42697807536). NSE and Yahoo both answered GitHub's runners, so the refresh needs no local fallback. The run:
  - fetched 5 new filings and 1,134 price bars, with no errors;
  - compacted the snapshot to 3.2 MB;
  - committed it as `github-actions[bot]`;
  - set off a Vercel redeploy.

  The first run had failed for a different reason: `astral-sh/setup-uv` publishes full version tags only, so the workflow now pins `v10.3.0`.

A live build is saved only on the instance that ran it, so another instance can answer 404 for it later. The app keeps a dossier it built in the current tab whatever the server says.

