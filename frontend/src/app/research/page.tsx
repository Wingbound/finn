"use client";

import { DossierList } from "@/components/research/DossierList";
import { SearchBox } from "@/components/research/SearchBox";
import { ErrorState, Skeleton } from "@/components/States";
import { useResearchList } from "@/lib/hooks";

export default function ResearchPage() {
  const { data, error, mutate } = useResearchList();
  return (
    <>
      <header className="pt-2 pb-4">
        <h1 className="text-section font-semibold">Research</h1>
        <p className="text-ink-2">
          Any NSE company. FINN reads its last four earnings calls and latest annual report, then checks what management
          promised against what happened.
        </p>
      </header>
      <SearchBox known={new Set(data?.map((d) => d.symbol) ?? [])} />
      <section aria-labelledby="ready" className="pt-6">
        <h2 id="ready" className="pb-2 text-title font-semibold">
          Ready to read
        </h2>
        {error && !data ? <ErrorState message={error.message} onRetry={() => mutate()} /> : null}
        {!data && !error ? <Skeleton lines={5} label="Loading dossiers" /> : null}
        {data ? (
          data.length ? (
            <DossierList items={data} />
          ) : (
            <p className="text-ink-2">No dossiers yet. Search a company to build the first.</p>
          )
        ) : null}
      </section>
    </>
  );
}
