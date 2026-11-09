// Plan 6 Task 3: copy and touch targets the final review deferred.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CitationChip } from "@/components/dossier/CitationChip";
import { DossierList } from "@/components/research/DossierList";
import { friendlyBuildError } from "@/lib/sse";

describe("copy", () => {
  it("counts one promise in the singular", () => {
    render(
      <DossierList
        items={[{ symbol: "ABC", name: "Abc", built_at: "2026-11-09T10:00:00+05:30", counts: { sources: 1, ledger_rows: 1, bull: 0, bear: 0, notes: 0, ledger: { pending: 1 } } }]}
      />,
    );
    expect(screen.getByText(/1 promise tracked/)).toBeInTheDocument();
  });

  it("explains server build errors in plain words", () => {
    expect(friendlyBuildError("build timed out")).toMatch(/ran out of time/);
    expect(friendlyBuildError("build failed: RuntimeError")).toMatch(/error on the server/);
    expect(friendlyBuildError("ZZZZ not found on screener")).toBe("ZZZZ not found on screener");
  });
});

describe("touch targets", () => {
  it("makes citation chips at least 44 px tall", () => {
    render(<CitationChip citation={{ source_id: "FACTS", page: 0, quote: "x" }} sources={[]} onOpen={() => {}} />);
    expect(screen.getByRole("button").className).toMatch(/min-h-11/);
  });
});
