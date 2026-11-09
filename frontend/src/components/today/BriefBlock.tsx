import type { Brief } from "@/lib/types";

export function BriefBlock({ brief }: { brief: Brief }) {
  return (
    <div className="mt-1.5">
      <p>{brief.one_liner}</p>
      {brief.facts.length ? (
        <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-3 gap-y-1 text-caption">
          {brief.facts.map((f) => (
            <div key={f.label} className="contents">
              <dt className="text-ink-2">{f.label}</dt>
              <dd className="font-medium">{f.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {brief.quote ? <blockquote className="quote mt-2 border-l-2 border-rule pl-3 text-ink">{brief.quote}</blockquote> : null}
    </div>
  );
}
