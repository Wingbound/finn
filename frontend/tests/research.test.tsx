import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const build = vi.fn();
vi.mock("@/lib/sse", async (orig) => ({ ...(await orig<typeof import("@/lib/sse")>()), buildDossier: (...a: unknown[]) => build(...a) }));

import { BuildProgress } from "@/components/research/BuildProgress";
import { Tally } from "@/components/Tally";
import { BuildError, STOPPED } from "@/lib/sse";

beforeEach(() => {
  build.mockReset(); // a returned function would run as teardown
});
afterEach(() => vi.useRealTimers());

describe("BuildProgress", () => {
  it("lists progress as it arrives and hands over the dossier when done", async () => {
    let finish: (v: unknown) => void = () => {};
    build.mockImplementation((_s: string, { onProgress }: { onProgress: (m: string) => void }) => {
      onProgress("Resolving ABC on screener");
      onProgress("Reading Q2 FY27 earnings call");
      return new Promise((r) => (finish = r));
    });
    const done = vi.fn();
    render(<BuildProgress symbol="ABC" onDone={done} />);
    expect(await screen.findByText("Reading Q2 FY27 earnings call")).toBeInTheDocument();
    expect(screen.getByText("Resolving ABC on screener")).toBeInTheDocument();
    const result = { dossier: { symbol: "ABC" }, excerpts: {} };
    await act(async () => finish(result));
    expect(done).toHaveBeenCalledWith(result);
  });
  it("shows the server's reason and retries", async () => {
    build.mockRejectedValueOnce(new BuildError("error", "ZZZZ not found on screener"));
    build.mockImplementationOnce(() => new Promise(() => {}));
    render(<BuildProgress symbol="ZZZZ" onDone={() => {}} />);
    expect(await screen.findByText("ZZZZ not found on screener")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(build).toHaveBeenCalledTimes(2));
  });
  it("says when the stream stopped early", async () => {
    build.mockRejectedValueOnce(new BuildError("incomplete", STOPPED));
    render(<BuildProgress symbol="ABC" onDone={() => {}} />);
    expect(await screen.findByText(/The build stopped before finishing/)).toBeInTheDocument();
  });
  it("cancels", async () => {
    let signal: AbortSignal | undefined;
    build.mockImplementation((_s: string, o: { signal: AbortSignal }) => {
      signal = o.signal;
      return new Promise(() => {});
    });
    const cancel = vi.fn();
    render(<BuildProgress symbol="ABC" onDone={() => {}} onCancel={cancel} />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(signal?.aborted).toBe(true);
    expect(cancel).toHaveBeenCalled();
  });
});

describe("Tally", () => {
  it("states every count in words and draws proportional segments", () => {
    const { container } = render(<Tally counts={{ kept: 2, missed: 1, pending: 8, dropped: 1 }} />);
    expect(screen.getByText("2 kept, 1 missed, 8 pending, 1 not mentioned again")).toBeInTheDocument();
    const segs = [...container.querySelectorAll("[data-status]")] as HTMLElement[];
    expect(segs.map((s) => s.dataset.status)).toEqual(["kept", "missed", "pending", "dropped"]);
    expect(segs[2]?.style.flexGrow).toBe("8");
  });
  it("renders nothing for an empty ledger", () => {
    const { container } = render(<Tally counts={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("BuildProgress after a dropped stream (final review I3)", () => {
  it("offers to look for the saved copy", async () => {
    build.mockRejectedValueOnce(new BuildError("incomplete", STOPPED));
    const check = vi.fn();
    render(<BuildProgress symbol="ABC" onDone={() => {}} onCheckSaved={check} />);
    fireEvent.click(await screen.findByRole("button", { name: "Check for a saved copy" }));
    expect(check).toHaveBeenCalled();
  });
  it("treats an unexpected failure as a stopped build, not a failed one", async () => {
    build.mockRejectedValueOnce(new TypeError("network error"));
    render(<BuildProgress symbol="ABC" onDone={() => {}} onCheckSaved={() => {}} />);
    expect(await screen.findByText(/The build stopped before finishing/)).toBeInTheDocument();
  });
});
