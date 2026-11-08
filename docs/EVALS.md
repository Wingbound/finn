# FINN evals

## 1. Filing classification

`backend/scripts/eval_classify.py` scores the classifier against a labelled gold set,
`backend/tests/fixtures/gold/classification.jsonl`.

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
- **Misses:** each miss is listed as seq_id · gold → predicted · subject[:80].

### Results (run 2026-11-08)

| mode | overall accuracy | material-category accuracy | rules coverage |
|---|---|---|---|
| Rules only (`--no-llm`) | 85.6% (89/104) | 84.8% (39/46) | 80.8% (84/104) |
| Rules + LLM | **pending API keys.** Run `uv run python scripts/eval_classify.py` | target ≥ 90% | 80.8% (same rules) |

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

### Live snapshot

The 30-day seed `backend/seed/finn.sqlite` was built on 2026-11-08 with
`scripts/refresh.py --days 30 --no-llm`. Rules classified 253 of its 317 filings (79.8%). The
other 64 took the `unclassified` default, pending the LLM re-run.
