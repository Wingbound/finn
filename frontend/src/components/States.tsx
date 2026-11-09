"use client";

/** Grey bars where content will land; announced once as loading. */
export function Skeleton({ lines = 6, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-3 py-4">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-well" style={{ width: `${92 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  );
}

/** What went wrong, and the one thing to do about it. */
export function ErrorState({ message, onRetry, note }: { message: string; onRetry?: () => void; note?: string }) {
  return (
    <div role="alert" className="my-4 border-l-2 border-missed py-1 pl-3">
      <p className="font-medium">{message}</p>
      <p className="text-caption text-ink-2">
        {note ?? "Check your connection, then try again. The server may be waking up."}
      </p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="mt-2 min-h-11 font-semibold text-pencil">
          Retry
        </button>
      ) : null}
    </div>
  );
}

/** A two-to-four way choice that reads as one control. */
export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex rounded-lg bg-well p-0.5">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`min-h-10 flex-1 rounded-md px-2 text-caption ${
              on ? "bg-paper font-semibold text-ink shadow-[0_0_0_1px_var(--rule)]" : "text-ink-2"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
