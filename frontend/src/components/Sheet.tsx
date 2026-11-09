"use client";

import { useEffect, useRef } from "react";

/** A bottom sheet on a native <dialog> (focus trap, Esc to close, inert page behind). */
export function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-label={title}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // a tap on the backdrop
      }}
    >
      <div className="flex max-h-[88dvh] flex-col">
        <div className="flex items-center justify-between gap-4 border-b border-rule px-4 py-2">
          <h2 className="text-title font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="min-h-11 px-2 text-pencil">
            Close
          </button>
        </div>
        <div className="overflow-y-auto px-4 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]">{open ? children : null}</div>
      </div>
    </dialog>
  );
}
