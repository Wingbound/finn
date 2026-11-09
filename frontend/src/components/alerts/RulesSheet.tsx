"use client";

import { useState } from "react";
import { Sheet } from "@/components/Sheet";
import { categoryLabel } from "@/lib/format";
import { DEFAULT_RULES, KEYS, LIMITS, useStored, validateRules } from "@/lib/store";
import { CATEGORIES, type Category, type Rules } from "@/lib/types";

const PICKABLE = CATEGORIES.filter((c) => c !== "unclassified");
const parse = (s: string): number | null => {
  const n = Number.parseFloat(s);
  return Number.isFinite(n) ? n : null;
};

function NumberField({
  label,
  value,
  onChange,
  step,
  limits,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step: number;
  limits: readonly [number, number];
  placeholder?: string;
}) {
  const bump = (dir: 1 | -1) => {
    const n = parse(value) ?? parse(placeholder ?? "") ?? limits[0];
    onChange(String(Math.min(limits[1], Math.max(limits[0], Math.round((n + dir * step) * 10) / 10))));
  };
  return (
    <div className="flex items-center gap-2">
      <button type="button" onClick={() => bump(-1)} aria-label={`Lower ${label.toLowerCase()}`} className="h-11 w-11 rounded-lg border border-rule text-title">
        −
      </button>
      <input
        aria-label={label}
        inputMode="decimal"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 w-20 rounded-lg border border-rule bg-paper text-center"
      />
      <button type="button" onClick={() => bump(1)} aria-label={`Raise ${label.toLowerCase()}`} className="h-11 w-11 rounded-lg border border-rule text-title">
        +
      </button>
    </div>
  );
}

type Draft = {
  volume: string;
  price: string;
  categories: Set<Category>;
  overrides: Record<string, { volume: string; price: string; muted: boolean }>;
};

const toDraft = (r: Rules): Draft => ({
  volume: String(r.volume_multiple),
  price: String(r.price_move_pct),
  categories: new Set(r.categories),
  overrides: Object.fromEntries(
    Object.entries(r.overrides).map(([s, o]) => [
      s,
      { volume: o.volume_multiple?.toString() ?? "", price: o.price_move_pct?.toString() ?? "", muted: o.muted },
    ]),
  ),
});

const fromDraft = (d: Draft, base: Rules): Rules | null =>
  validateRules({
    ...base,
    volume_multiple: parse(d.volume) ?? base.volume_multiple,
    price_move_pct: parse(d.price) ?? base.price_move_pct,
    categories: [...d.categories],
    overrides: Object.fromEntries(
      Object.entries(d.overrides).map(([s, o]) => [
        s,
        { volume_multiple: parse(o.volume), price_move_pct: parse(o.price), muted: o.muted },
      ]),
    ),
  });

export function RulesSheet({
  open,
  onClose,
  symbols,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  symbols: string[];
  onSaved?: () => void;
}) {
  const [rules, setRules] = useStored(KEYS.rules, DEFAULT_RULES, validateRules);
  const [draft, setDraft] = useState<Draft | null>(null);
  const d = draft ?? toDraft(rules);
  const edit = (patch: Partial<Draft>) => setDraft({ ...d, ...patch });
  const free = symbols.filter((s) => !(s in d.overrides));

  const close = () => {
    setDraft(null);
    onClose();
  };
  const save = () => {
    const next = fromDraft(d, rules);
    if (next) setRules(next);
    setDraft(null);
    onSaved?.();
    onClose();
  };

  return (
    <Sheet open={open} onClose={close} title="Alert rules">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
        className="space-y-6"
      >
        <fieldset className="space-y-3">
          <legend className="text-caption text-ink-2">Alert me when, for any stock</legend>
          <div className="flex items-center justify-between gap-3">
            <span>Volume is at least this many times its 20-day average</span>
            <NumberField label="Volume multiple" value={d.volume} onChange={(v) => edit({ volume: v })} step={0.5} limits={LIMITS.volume_multiple} />
          </div>
          <div className="flex items-center justify-between gap-3">
            <span>The price moves at least this much in a day</span>
            <NumberField label="Price move (%)" value={d.price} onChange={(v) => edit({ price: v })} step={0.5} limits={LIMITS.price_move_pct} />
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-caption text-ink-2">And for these filings</legend>
          <div className="mt-1 grid grid-cols-2 gap-x-3">
            {PICKABLE.map((c) => (
              <label key={c} className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  className="h-5 w-5 accent-[var(--pencil)]"
                  checked={d.categories.has(c)}
                  onChange={(e) => {
                    const next = new Set(d.categories);
                    if (e.target.checked) next.add(c);
                    else next.delete(c);
                    edit({ categories: next });
                  }}
                />
                {categoryLabel(c)}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-caption text-ink-2">Stock overrides (blank uses the rule above)</legend>
          {Object.entries(d.overrides).map(([sym, o]) => (
            <div key={sym} className="flex flex-wrap items-center gap-2 border-t border-rule py-2">
              <span className="w-24 font-semibold">{sym}</span>
              <input
                aria-label={`Volume multiple for ${sym}`}
                inputMode="decimal"
                placeholder={d.volume}
                value={o.volume}
                onChange={(e) => edit({ overrides: { ...d.overrides, [sym]: { ...o, volume: e.target.value } } })}
                className="h-11 w-16 rounded-lg border border-rule bg-paper text-center"
              />
              <span className="text-caption text-ink-2">×</span>
              <input
                aria-label={`Price move for ${sym}`}
                inputMode="decimal"
                placeholder={d.price}
                value={o.price}
                onChange={(e) => edit({ overrides: { ...d.overrides, [sym]: { ...o, price: e.target.value } } })}
                className="h-11 w-16 rounded-lg border border-rule bg-paper text-center"
              />
              <span className="text-caption text-ink-2">%</span>
              <label className="flex min-h-11 items-center gap-1.5">
                <input
                  type="checkbox"
                  aria-label={`Mute ${sym}`}
                  className="h-5 w-5 accent-[var(--pencil)]"
                  checked={o.muted}
                  onChange={(e) => edit({ overrides: { ...d.overrides, [sym]: { ...o, muted: e.target.checked } } })}
                />
                Mute
              </label>
              <button
                type="button"
                className="ml-auto min-h-11 text-caption text-ink-2"
                onClick={() => {
                  const rest = { ...d.overrides };
                  delete rest[sym];
                  edit({ overrides: rest });
                }}
              >
                Remove
              </button>
            </div>
          ))}
          {free.length ? (
            <select
              aria-label="Add a stock"
              value=""
              onChange={(e) => e.target.value && edit({ overrides: { ...d.overrides, [e.target.value]: { volume: "", price: "", muted: false } } })}
              className="h-11 w-full rounded-lg border border-rule bg-paper px-3"
            >
              <option value="">Add a stock…</option>
              {free.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          ) : null}
        </fieldset>

        <div className="flex items-center gap-3 pb-2">
          <button type="submit" className="min-h-11 flex-1 rounded-lg bg-pencil font-semibold text-paper">
            Save rules
          </button>
          <button type="button" onClick={() => setDraft(toDraft(DEFAULT_RULES))} className="min-h-11 px-3 text-pencil">
            Reset to defaults
          </button>
        </div>
      </form>
    </Sheet>
  );
}
