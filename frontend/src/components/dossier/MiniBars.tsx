"use client";

import { useState } from "react";

const TOP = 6;

/** Bars from a zero baseline: positives up, negatives down, nulls skipped. */
export function barGeometry(values: (number | null)[], W: number, H: number) {
  const nums = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!nums.length) return { bars: [] as Bar[], zero: H, band: 0 };
  const lo = Math.min(0, ...nums);
  const hi = Math.max(0, ...nums);
  const span = hi - lo || 1;
  const scale = (v: number) => TOP + ((hi - v) / span) * (H - TOP);
  const zero = scale(0);
  const band = W / values.length;
  const w = Math.min(28, band * 0.62);
  const bars: Bar[] = [];
  values.forEach((v, i) => {
    if (typeof v !== "number" || !Number.isFinite(v)) return;
    const x = i * band + (band - w) / 2;
    const y = v >= 0 ? scale(v) : zero;
    const h = Math.max(v >= 0 ? zero - scale(v) : scale(v) - zero, 1);
    bars.push({ i, x, y, w, h, value: v });
  });
  return { bars, zero, band };
}

export interface Bar {
  i: number;
  x: number;
  y: number;
  w: number;
  h: number;
  value: number;
}

/** A bar with 4px rounding only at its data end. */
function barPath(b: Bar, up: boolean): string {
  const r = Math.min(4, b.w / 2, b.h);
  const { x, y, w, h } = b;
  return up
    ? `M${x} ${y + h}V${y + r}Q${x} ${y} ${x + r} ${y}H${x + w - r}Q${x + w} ${y} ${x + w} ${y + r}V${y + h}Z`
    : `M${x} ${y}V${y + h - r}Q${x} ${y + h} ${x + r} ${y + h}H${x + w - r}Q${x + w} ${y + h} ${x + w} ${y + h - r}V${y}Z`;
}

export const fyLabel = (y: string) => {
  const m = y.match(/(\d{4})/);
  return m ? `FY${m[1]!.slice(2)}` : y;
};

const W = 320;
const H = 72;

/** One series of yearly bars with a readout that follows the finger. */
export function MiniBars({
  title,
  years,
  values,
  format,
  summary,
}: {
  title: string;
  years: string[];
  values: (number | null)[];
  format: (v: number) => string;
  summary?: string;
}) {
  const { bars, zero, band } = barGeometry(values, W, H);
  const last = bars.at(-1);
  const [active, setActive] = useState<number | null>(null);
  const shown = bars.find((b) => b.i === active) ?? last;
  const negative = bars.some((b) => b.value < 0);
  return (
    <figure className="py-2">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="font-semibold">{title}</span>
        <span className="text-caption text-ink-2">{summary}</span>
      </figcaption>
      <p className="text-caption" aria-live="polite">
        {shown ? `${fyLabel(years[shown.i] ?? "")}: ${format(shown.value)}` : "No figures"}
      </p>
      <svg
        viewBox={`0 0 ${W} ${H + 16}`}
        className="mt-1 block w-full touch-none"
        role="img"
        aria-label={`${title} by year: ${bars.map((b) => `${fyLabel(years[b.i] ?? "")} ${format(b.value)}`).join(", ")}`}
        onPointerLeave={() => setActive(null)}
      >
        <line x1={0} x2={W} y1={zero} y2={zero} stroke="var(--rule)" strokeWidth={1} />
        {bars.map((b) => (
          <path
            key={b.i}
            d={barPath(b, b.value >= 0)}
            fill={b.i === (active ?? last?.i) ? "var(--ink)" : "var(--ink-2)"}
            opacity={b.i === (active ?? last?.i) ? 1 : 0.55}
          />
        ))}
        {years.map((y, i) => (
          <text key={y} x={i * band + band / 2} y={H + 13} textAnchor="middle" fontSize={10} fill="var(--ink-2)">
            {fyLabel(y)}
          </text>
        ))}
        {years.map((y, i) => (
          <rect
            key={`hit-${y}`}
            x={i * band}
            y={0}
            width={band}
            height={H + 16}
            fill="transparent"
            onPointerEnter={() => setActive(i)}
            onPointerDown={() => setActive(i)}
          />
        ))}
      </svg>
      {negative ? <p className="sr-only">Bars below the line are losses.</p> : null}
    </figure>
  );
}

/** One series as a 2px line with the latest point marked. */
export function MiniLine({
  title,
  years,
  values,
  format,
  summary,
}: {
  title: string;
  years: string[];
  values: (number | null)[];
  format: (v: number) => string;
  summary?: string;
}) {
  const nums = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const lo = nums.length ? Math.min(...nums) : 0;
  const hi = nums.length ? Math.max(...nums) : 1;
  const pad = (hi - lo) * 0.15 || 1;
  const band = W / Math.max(values.length, 1);
  const pts = values
    .map((v, i) => (typeof v === "number" && Number.isFinite(v) ? { i, v, x: i * band + band / 2, y: TOP + ((hi + pad - v) / (hi - lo + 2 * pad)) * (H - TOP * 2) } : null))
    .filter((p): p is { i: number; v: number; x: number; y: number } => p !== null);
  const [active, setActive] = useState<number | null>(null);
  const shown = pts.find((p) => p.i === active) ?? pts.at(-1);
  const d = pts.map((p, k) => `${k ? "L" : "M"}${p.x} ${p.y}`).join("");
  return (
    <figure className="py-2">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="font-semibold">{title}</span>
        <span className="text-caption text-ink-2">{summary}</span>
      </figcaption>
      <p className="text-caption" aria-live="polite">
        {shown ? `${fyLabel(years[shown.i] ?? "")}: ${format(shown.v)}` : "No figures"}
      </p>
      <svg
        viewBox={`0 0 ${W} ${H + 16}`}
        className="mt-1 block w-full touch-none"
        role="img"
        aria-label={`${title} by year: ${pts.map((p) => `${fyLabel(years[p.i] ?? "")} ${format(p.v)}`).join(", ")}`}
        onPointerLeave={() => setActive(null)}
      >
        <path d={d} fill="none" stroke="var(--ink)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {shown ? <circle cx={shown.x} cy={shown.y} r={4} fill="var(--ink)" stroke="var(--paper)" strokeWidth={2} /> : null}
        {years.map((y, i) => (
          <text key={y} x={i * band + band / 2} y={H + 13} textAnchor="middle" fontSize={10} fill="var(--ink-2)">
            {fyLabel(y)}
          </text>
        ))}
        {years.map((y, i) => (
          <rect key={`hit-${y}`} x={i * band} y={0} width={band} height={H + 16} fill="transparent" onPointerEnter={() => setActive(i)} onPointerDown={() => setActive(i)} />
        ))}
      </svg>
    </figure>
  );
}
