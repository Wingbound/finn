# Plan 7 final review (f930c13..265bda4)

Verified: backend pytest 892 passed, ruff clean, frontend vitest 201 passed. One live read-only NSE call made: get_stock_history RELIANCE months=3 returned 63 bars (2026-08-10..2026-11-09), chunk_months=3, so a single call covers the 3-month window. Yahoo's "3mo" gives about the same, so the 60-bar HISTORY_BARS and the alert path (max(60, lookback+ALERT_SESSIONS+1)) are no worse than before. The recorded fixtures are 1-month responses (20 bars); no fixture covers months=3, which is fine.

## Critical
None.

## Important
1. Partial or stale NSE history is accepted without fallback. backend/finn/ingest/nse_mcp.py:165-168 and backend/scripts/refresh.py `from_nse = {b.symbol for b in bars}`. Any symbol with at least one parsed bar counts as served by NSE. Scenario: NSE returns 1-5 rows (new listing, a truncated chunk, rows dropped as malformed by `_bars`) or a last date lagging the other symbols (the server serves "in-memory-cache", which could be updated per symbol). Yahoo is never asked, the store keeps a thin or stale series, the volume-spike baseline (20 prior bars) and sparkline degrade silently, and meta says "NSE end-of-day" with no error. The plan says "error, timeout, empty" fall back, but "fewer than needed" is a quiet gap. Fix: in fetch_nse_eod, treat a symbol as failed (reason "only N bars" or "last bar D older than D_max") when len(got) < ~25 or its last date is earlier than the newest last date across symbols. Add a test for each.
2. Mixed provenance label is wrong when a fallback or partial failure leaves old data. refresh.py `prices_source` is set from this run's symbols only. If Yahoo raises for the missing symbols (errors gets "prices: ..."), the store still holds their older bars but the caption says "NSE end-of-day" with a fresh as_of. Fix: when prices_missing is non-empty, include it in the source string (for example "NSE end-of-day (Yahoo for 3, 2 not updated)") or leave the label naming partial. The caption is the only place a user would learn about it, since errors only go to the CI summary.

## Minor
1. Caption grammar with the mixed source. frontend/src/components/alerts/Holdings.tsx priceCaption yields "NSE end-of-day (Yahoo for 3) prices, as of 10 Nov, 06:02." Reads oddly; the 3 is not meaningful to a reader. Fix: lead with `${source}` as its own sentence, e.g. "Prices: NSE end-of-day (Yahoo for 3). As of ..." or keep the Yahoo count out of the UI string. Test only covers the plain forms.
2. "as of 10 Nov, 06:02" is the fetch time (prices_as_of = fetched_at), now sitting next to "NSE end-of-day prices", which suggests the data is from 10 Nov while the latest official close is 9 Nov. Pre-existing semantics, but the new wording sharpens it. Consider showing the last session date from the bars.
3. Unhandled shapes in the client. nse_mcp.py:108-110: `msg['error'].get(...)` raises AttributeError if error is a string, and a non-dict JSON body (list/batch) breaks `"error" in msg`/`.get`. AttributeError is not in the `except (NseMcpError, httpx.HTTPError, ValueError)`, so it escapes fetch_nse_eod; refresh.py then catches it and discards every NSE bar already fetched (all symbols go to Yahoo). Fix: validate `isinstance(msg, dict)` and the error shape in `call`, raising NseMcpError.
4. SSE parsing takes the last `data:` line without matching the request id (nse_mcp.py:_payload). A trailing log or progress notification would shadow the result. Fix: pick the message whose "id" equals the request id.
5. No session recovery and no circuit breaker. A 404/expired session or a hung server makes each of the remaining symbols fail on its own (up to 20 s each, about 6 minutes for 18 symbols) before Yahoo is tried. Fix: stop after 2-3 consecutive transport errors and fail the rest at once; optionally re-open once on 404.
6. `_bars` drops malformed rows silently and falls back to non-EQ rows when no EQ rows exist (`or rows`). Log a count of dropped rows; consider not accepting non-EQ series. Rows with close 0 or NaN are not rejected.
7. Test gaps. Not covered: plain-JSON (non-SSE) responses, `isError: true`, string `error`, malformed rows, short or stale history, Yahoo raising while NSE gave some symbols, and exit_code for the new paths (unchanged logic, but untested with the new flow). conftest's autouse fixture is guarded by `hasattr(refresh_mod, "fetch_nse_eod")`, so if the import is renamed the guard silently stops protecting and tests could go live; drop the guard (fail loudly), or raise on any real network use. The "Yahoo raising" print "keeping existing prices" is now misleading when NSE bars were stored.
8. Mixing NSE and old Yahoo bars: safe in the store. upsert overwrites by (symbol, date), so NSE closes replace Yahoo partials for overlapping dates, and Yahoo weekend/Muhurat bars are still filtered at read time by completed_sessions (the live NSE response did not include Sun 2026-11-08, and completed_sessions would drop it anyway). Volumes differ slightly between sources across the join, which is negligible for a 20-day baseline.

## Checked and fine
- Session handling: Mcp-Session-Id read from initialize and sent on every later request (including notifications/initialized); a missing header tolerated; protocol header sent. Tested.
- SSE vs JSON parsing, `{"error": ...}` text with isError false (real fixture), JSON-RPC error, HTTP >= 400, timeouts (httpx.HTTPError caught).
- Fallback runs only for symbols without bars; both-down case keeps today's error and exit codes; NSE-only fully down is not an error. fetched_at set before and re-set after Yahoo; all-NSE case gets a fresh prices_as_of. Exit-code contract (0/1/2/4) unchanged: NSE failures add no errors, and price_bars/errors drive exit_code as before.
- /portfolio `source` is additive and optional in the TS type; older snapshots without the meta render the old caption.

## Declined to judge
- NSE terms of use (educational and research only): the plan acknowledges it and README mention is a plan item; not verified in the diff (no README change in the package).
- Workflow/Vercel deploy behavior of refresh.yml: outside the diff.

## Verdict
Approved with fixes: no Critical issues; address Important 1 and 2 (cheap) before the final push, the Minor items are optional.
