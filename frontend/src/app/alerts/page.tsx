"use client";

import { useState } from "react";
import { AlertLog } from "@/components/alerts/AlertLog";
import { Holdings } from "@/components/alerts/Holdings";
import { RulesSheet } from "@/components/alerts/RulesSheet";
import { ErrorState, Skeleton } from "@/components/States";
import { day, plural, stamp } from "@/lib/format";
import { useAlerts, usePortfolio } from "@/lib/hooks";
import { DEFAULT_RULES, KEYS, useStored, validateRules } from "@/lib/store";

export default function AlertsPage() {
  const [rules, , ready] = useStored(KEYS.rules, DEFAULT_RULES, validateRules);
  const alerts = useAlerts(ready ? rules : null);
  const portfolio = usePortfolio();
  const [sheet, setSheet] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const flagged = new Set(alerts.data?.alerts.map((a) => a.symbol) ?? []);
  const symbols = portfolio.data?.holdings.map((h) => h.symbol) ?? [];
  const saved = () => {
    setToast("Rules saved");
    setTimeout(() => setToast(null), 2500);
  };

  return (
    <>
      <header className="flex items-start justify-between gap-3 pt-2 pb-3">
        <div>
          <h1 className="text-section font-semibold">Alerts</h1>
          <p className="text-caption text-ink-2">
            Volume over {rules.volume_multiple}× its average, or a {rules.price_move_pct}% day move, plus{" "}
            {plural(rules.categories.length, "filing type")}.
          </p>
        </div>
        <button type="button" onClick={() => setSheet(true)} className="min-h-11 shrink-0 rounded-lg border border-rule px-3 font-medium text-pencil">
          Edit rules
        </button>
      </header>

      <section aria-labelledby="log">
        <h2 id="log" className="pt-2 pb-1 text-title font-semibold">
          {alerts.data ? `${plural(alerts.data.alerts.length, "alert")} this week` : "This week"}
        </h2>
        {alerts.data ? (
          <p className="pb-2 text-caption text-ink-2">
            {day(alerts.data.window.start)} to {day(alerts.data.window.end)}
          </p>
        ) : null}
        {alerts.error && !alerts.data ? <ErrorState message={alerts.error.message} onRetry={() => alerts.mutate()} /> : null}
        {!alerts.data && !alerts.error ? <Skeleton lines={4} label="Loading alerts" /> : null}
        {alerts.data ? <AlertLog alerts={alerts.data.alerts} /> : null}
      </section>

      <section aria-labelledby="holdings" className="pt-6">
        <h2 id="holdings" className="pb-1 text-title font-semibold">
          Holdings
        </h2>
        {portfolio.data?.as_of ? (
          <p className="pb-2 text-caption text-ink-2">Prices as of {stamp(portfolio.data.as_of)}. Day change and volume use the last full session.</p>
        ) : null}
        {portfolio.error && !portfolio.data ? <ErrorState message={portfolio.error.message} onRetry={() => portfolio.mutate()} /> : null}
        {!portfolio.data && !portfolio.error ? <Skeleton lines={6} label="Loading holdings" /> : null}
        {portfolio.data ? <Holdings rows={portfolio.data.holdings} rules={rules} flagged={flagged} /> : null}
      </section>

      <RulesSheet open={sheet} onClose={() => setSheet(false)} symbols={symbols} onSaved={saved} />
      {toast ? (
        <p role="status" className="fixed inset-x-0 bottom-20 z-30 mx-auto w-fit rounded-lg bg-ink px-4 py-2 text-paper">
          {toast}
        </p>
      ) : null}
    </>
  );
}
