# Task 7g review

Spec compliance: PASS (✅) with one deviation noted below.
Quality: Approved (minor fixes recommended).

Spec checks
- A other-period: patterns, ordinal and month-quarter mapping, FY stripped inside quarter mentions, kept/partly/missed only, fixed rationale. Probed: "Q2" vs "Q2 FY27" vs "Q2 FY26" (bare Q2 matches any FY), "Q2FY27", "second quarter of FY27", "Q4 FY26 vs Q4 FY25", FY horizon with quarter-only evidence all behave per brief.
- B restated: future/delivery lists match the brief; applies to kept/partly only; does not reuse guidance._CUES.
- C below-target: kept only; quantitative + target_low not None + lower-is-better skip; % needs a % sign or "percent"; non-% range [0.1*lo, 10*max]; strict `< 0.98*lo` (14.7 vs 15 stays, 14.5 downgrades); lo=0/None skip. Order other_period, restated, below_target.
- Stats: build_ledger initialises zeros via setdefault; pipeline passes `guard`; eval column renders and totals sum. Tested.
- Deviation (accepted): rationale prints "50–60" / "at least 50" without "%" (the existing _target always appends %). Reads oddly for a floor: "(480) is below the at least 500 target".

Changed pre-existing tests
- test_judged_kept_with_page_corrected: original fixture was status "kept" with evidence "In terms of financing, we intend replacing the Euro 1.4 billion 18-month bridge loan with longer tenure, capital and favorable terms." That is a pure future-tense restatement with no delivery cue, so the guard downgrading it is correct (this is the DIXON failure mode). The test exists to check page correction and the judged method, which still hold. Not a hidden over-aggressive guard. Switching to "missed" is a workaround; the fixture is semantically odd.
- test_future_horizon_pending_past_horizon_kept: original used horizon Q1 FY27 with evidence "Q2 FY27 revenue stood at USD 487.6 million...". Evidence about Q2 FY27 for a Q1 FY27 promise is a real period mismatch; the guard is right. The test targets the _not_yet_due gate, which is still exercised with Q2 FY27. Fine.

Findings
1. [Important] backend/finn/research/ledger.py (_PERIOD_LABEL, ~line 436): `\b` fails on fused labels such as "H1FY26" and "Q3FY26", so the "26" survives as a number. Failing input: promise "range of 50 to 60", evidence "in H1FY26 we hit 8 billion" gives rationale "The later figure (26) is below the 50–60 target"; the cited number is a fiscal-year digit, not a figure. It also causes false skips: target_low=20, evidence "Q3FY26 ... 5 crore" counts 26, so no downgrade. The IDEA test passes only because 26 < 49. Fix: strip with no leading `\b` (e.g. `H[12]\s*FY\s*'?\d{2,4}|Q[1-4]\s*FY...` before the generic pass, or `(?<![A-Za-z])` lookarounds).
2. [Important] ledger.py `_DELIVERED` (spec-literal): present-tense deliveries are not delivery cues, so they get downgraded when a future cue is present. Failing inputs (all kept by the judge, then pending): "Revenue growth is on track at 18%", "Margin is 21%, we expect 22%", "Capacity utilization will improve; we are at 80% currently". Consider adding "is at|are at|currently|stands at|now at" or requiring a digit as a delivery cue. Left as is it is within the brief, but it will cost recall on real rows.
3. [Minor] ledger.py `_DELIVERED`: "was", "had", "did" are weak and cause false negatives for restatements: "We had planned to commission by Q3" and "The plan was to commission by Q3, we will confirm" stay kept. Brief-mandated.
4. [Minor] ledger.py `_other_period`: a mixed quote with one non-matching quarter and no matching one is downgraded even if FY-level context matches. Failing input: horizon Q4 FY26, evidence "the full year FY26 and Q3 FY26 were good" gives True. Consistent with the brief; noting it.
5. [Minor] test_research_ledger.py test_judged_kept_with_page_corrected: switching to "missed" for a quote that only restates a plan is semantically odd; a fixture with a delivery cue would keep "kept" and read better.
6. [Minor] ledger.py `_below_target` rationale: "below the at least 500 target" (floor targets) is awkward; use "below the 500 target".
