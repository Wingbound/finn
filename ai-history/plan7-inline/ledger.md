# SDD ledger — plan: docs/superpowers/plans/2026-11-10-plan7-nse-prices.md
Executor: inline on feat/nse-prices from main f930c13. User approved the switch ("yes") and keeping their first name in the AI history.
Task 1: implemented (live trial: 18/18 from NSE, 1,134 bars, 0 errors); review dispatched
Final review (sonnet): approved with fixes. Live: RELIANCE months=3 gives 63 bars, enough for the 60-bar alert history.
- Final: Ruling: minors 1 (caption wording), 3 (odd error shapes losing every NSE bar), 5 (a hung server stalling the refresh) and part of 7 (strict conftest guard, plain-JSON and isError tests) are fixed in the same pass — cheap, and they affect robustness or copy — cost if wrong: none.
Final: fixed I1 — test "thin_or_stale_history_is_left_for_the_fallback" + "partial_nse_bars_fill_in_when_yahoo_has_nothing" RED→GREEN
Final: fixed I2 — test "the_label_says_when_symbols_were_not_updated" RED→GREEN
Final: fixed minors 3/5/7 — tests "plain_json_answers_and_odd_error_shapes", "a_hung_server_trips_the_breaker" RED→GREEN; the conftest guard no longer uses hasattr
Final: fixed minor 1 — alerts.test caption RED→GREEN; "as of" is now taken after the last fetch (test_refresh fetch-time test)
Suite: pytest 897/897, vitest 201/201.
Final: minor (deferred): 2 "as of" is the fetch time, not the last session date; 4 SSE takes the last data line, without matching the id; 6 malformed rows are dropped silently, and non-EQ rows are used when there is no EQ
