import { act, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ListenButton } from "@/components/today/ListenButton";
import { briefScript } from "@/lib/briefScript";
import type { Digest } from "@/lib/types";

const load = (n: string): Digest => JSON.parse(readFileSync(join(__dirname, "fixtures", n), "utf8"));

describe("briefScript (Plan 8)", () => {
  it("opens with what matters in the window, reads at most six stories, and ends caught up", () => {
    const d = load("digest-7d.json");
    const lines = briefScript(d);
    expect(lines[0]).toBe("26 things matter in the last 7 days.");
    expect(lines).toContain("And 20 more on screen.");
    expect(lines.at(-2)).toBe("34 routine filings set aside.");
    expect(lines.at(-1)).toBe("You're caught up.");
    expect(lines).toHaveLength(1 + 6 + 1 + 2);
  });

  it("reads results as the filed growth figures, people as their change, deals as their one-liner", () => {
    const d = load("digest-7d.json");
    const [, tata, , , , , people, , deal] = d.stories;
    const lines = briefScript({ ...d, stories: [tata!, people!, deal!] });
    expect(lines[1]).toBe("Tata Steel: results. Revenue up 11.5 percent year on year, PAT up 16.2 percent.");
    expect(lines[2]).toMatch(/^Tata Steel: people\. Noel Naval Tata, retired as Non-Executive/);
    expect(lines[3]).toBe(
      "Tata Steel: deal. Tata Steel increased its equity stake in Creative Port Development Private Limited from 51% to 57.5% by converting preference shares.",
    );
  });

  it("says plainly when nothing matters, and counts one thing as one", () => {
    const d = load("digest-quiet.json");
    expect(briefScript({ ...d, counts: { ...d.counts, routine: 0 }, routine: {} })).toEqual([
      "Nothing matters in the last 24 hours.",
      "You're caught up.",
    ]);
    const one = load("digest-24h.json");
    expect(briefScript(one)[0]).toBe("1 thing matters in the last 24 hours.");
  });
});

describe("ListenButton (Plan 8)", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubSpeech() {
    const spoken: string[] = [];
    const synth = {
      speak: vi.fn((u: { text: string }) => spoken.push(u.text)),
      cancel: vi.fn(),
      getVoices: () => [{ lang: "en-US", name: "US" }, { lang: "en-IN", name: "India" }],
    };
    class Utterance {
      text: string;
      lang = "";
      voice: unknown = null;
      rate = 1;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) {
        this.text = text;
      }
    }
    vi.stubGlobal("speechSynthesis", synth);
    vi.stubGlobal("SpeechSynthesisUtterance", Utterance);
    return { synth, spoken };
  }

  it("speaks the lines in an Indian English voice, and stops on request", async () => {
    const { synth, spoken } = stubSpeech();
    render(<ListenButton lines={["2 things matter in the last 24 hours.", "You're caught up."]} />);
    const button = await screen.findByRole("button", { name: "Listen" });
    await act(async () => fireEvent.click(button));
    expect(spoken).toEqual(["2 things matter in the last 24 hours.", "You're caught up."]);
    const first = synth.speak.mock.calls[0]![0] as unknown as { voice: { lang: string } };
    expect(first.voice.lang).toBe("en-IN");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Stop listening" })));
    expect(synth.cancel).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Listen" })).toBeInTheDocument();
  });

  it("is not offered where the browser cannot speak", () => {
    vi.stubGlobal("speechSynthesis", undefined);
    render(<ListenButton lines={["x"]} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
