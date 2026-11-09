/** A blue-pencil stroke drawn once across its text: FINN striking what it set aside. */
export function PencilStrike({ children }: { children: React.ReactNode }) {
  return (
    <span className="relative inline-block">
      {children}
      <svg
        className="pointer-events-none absolute inset-x-[-3%] top-[38%] h-[30%] w-[106%] overflow-visible text-pencil"
        viewBox="0 0 100 10"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          className="pencil-draw"
          d="M1 6.5 C 22 4.8, 48 6.2, 70 4.6 S 92 4.2, 99 3.4"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.2}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </span>
  );
}
