"use client";

import { useState } from "react";
import { rupees } from "@/lib/format";

/** Points for a single series scaled into w×h with `pad` inset; a flat series sits mid-height. */
export function sparkPath(values: number[], w: number, h: number, pad: number) {
  const vs = values.filter((v) => Number.isFinite(v));
  if (!vs.length) return { d: "", points: [] as [number, number][] };
  const lo = Math.min(...vs);
  const hi = Math.max(...vs);
  const span = hi - lo;
  const step = vs.length > 1 ? (w - 2 * pad) / (vs.length - 1) : 0;
  const points = vs.map((v, i): [number, number] => {
    const x = vs.length > 1 ? pad + i * step : w / 2;
    const y = span === 0 ? h / 2 : pad + ((hi - v) / span) * (h - 2 * pad);
    return [Math.round(x * 100) / 100, Math.round(y * 100) / 100];
  });
  const d = points.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
  return { d, points };
}

const W = 72;
const H = 26;
const PAD = 3;

/** 20 closes as one thin line; touch or hover shows the close under the finger. */
export function Sparkline({ values }: { values: number[] }) {
  const { d, points } = sparkPath(values, W, H, PAD);
  const [hover, setHover] = useState<number | null>(null);
  if (!points.length) return <span className="inline-block w-[72px] text-caption text-ink-2">No prices</span>;
  const last = points[points.length - 1] as [number, number];
  const label = `20-day close, from ${rupees(values[0])} to ${rupees(values[values.length - 1])}`;
  const pick = (clientX: number, el: SVGSVGElement) => {
    const r = el.getBoundingClientRect();
    const x = ((clientX - r.left) / r.width) * W;
    let best = 0;
    points.forEach(([px], i) => {
      if (Math.abs(px - x) < Math.abs((points[best] as [number, number])[0] - x)) best = i;
    });
    setHover(best);
  };
  const hp = hover !== null ? points[hover] : undefined;
  return (
    <span className="relative inline-block">
      <svg
        role="img"
        aria-label={label}
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        className="block touch-none overflow-visible"
        onPointerMove={(e) => pick(e.clientX, e.currentTarget)}
        onPointerDown={(e) => pick(e.clientX, e.currentTarget)}
        onPointerLeave={() => setHover(null)}
      >
        <path d={d} fill="none" stroke="var(--ink-2)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={last[0]} cy={last[1]} r={2.5} fill="var(--ink)" />
        {hp ? (
          <>
            <line x1={hp[0]} x2={hp[0]} y1={0} y2={H} stroke="var(--rule)" strokeWidth={1} />
            <circle cx={hp[0]} cy={hp[1]} r={3} fill="var(--paper)" stroke="var(--ink)" strokeWidth={1.5} />
          </>
        ) : null}
      </svg>
      {hover !== null ? (
        <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 -translate-x-1/2 rounded-md bg-ink px-2 py-1 text-caption whitespace-nowrap text-paper">
          {rupees(values[hover])}
          {hover < values.length - 1 ? `, ${values.length - 1 - hover} sessions back` : ", last close"}
        </span>
      ) : null}
    </span>
  );
}
