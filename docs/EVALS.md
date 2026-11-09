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

### Live result

Live run over the 18 portfolio symbols: pending (controller)
