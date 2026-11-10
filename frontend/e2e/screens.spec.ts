// Screenshots for design review: SCREENS=<dir> npx playwright test e2e/screens.spec.ts
import { test } from "@playwright/test";
import { mockApi } from "./mock";

const DIR = process.env.SCREENS;
test.skip(!DIR, "set SCREENS=<dir> to capture");
test.use({ deviceScaleFactor: 2 });

const SHOTS: { name: string; path: string; digest?: string; prep?: (p: import("@playwright/test").Page) => Promise<void> }[] = [
  { name: "today", path: "/", digest: "digest-7d.json" },
  {
    name: "today-routine",
    path: "/",
    digest: "digest-24h.json",
    prep: async (p) => {
      await p.getByRole("button", { name: /routine filings set aside/ }).click();
      await p.waitForTimeout(600);
    },
  },
  { name: "today-empty", path: "/", digest: "digest-empty.json" },
  { name: "alerts", path: "/alerts" },
  { name: "dossier", path: "/research/PERSISTENT" },
  {
    name: "loop",
    path: "/",
    digest: "digest-7d.json",
    prep: async (p) => {
      await p.locator('[data-story^="ZYDUSLIFE:results"]').scrollIntoViewIfNeeded();
      await p.evaluate(() => document.querySelector('[data-story^="ZYDUSLIFE:results"] [aria-label="What management said"]')?.scrollIntoView({ block: "center" }));
    },
  },
  {
    name: "latest",
    path: "/research/ZYDUSLIFE",
    prep: async (p) => {
      await p.evaluate(() => document.getElementById("latest")?.scrollIntoView({ block: "start" }));
    },
  },
  {
    name: "trajectory",
    path: "/research/PERSISTENT",
    prep: async (p) => {
      await p.locator("#trajectory").scrollIntoViewIfNeeded();
      await p.evaluate(() => document.getElementById("trajectory")?.scrollIntoView({ block: "start" }));
    },
  },
  {
    name: "health",
    path: "/research/PERSISTENT",
    prep: async (p) => {
      await p.evaluate(() => document.getElementById("health")?.scrollIntoView({ block: "start" }));
    },
  },
  {
    name: "source",
    path: "/research/BAJFINANCE",
    prep: async (p) => {
      // the chip whose page the source fixture holds, so the highlight shows
      await p.getByRole("button", { name: "Q4 FY26 call (May 2026), p. 4" }).first().click();
      await p.waitForTimeout(600);
    },
  },
  {
    name: "research",
    path: "/research",
    prep: async (p) => {
      await p.getByLabel("Search a company or NSE symbol").fill("pi");
      await p.waitForTimeout(800);
    },
  },
  {
    name: "rules",
    path: "/alerts",
    prep: async (p) => {
      await p.getByRole("button", { name: "Edit rules" }).click();
      await p.waitForTimeout(300);
    },
  },
];

for (const scheme of ["light", "dark"] as const) {
  for (const s of SHOTS) {
    test(`${s.name} ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await mockApi(page, { digest: () => s.digest ?? "digest-7d.json" });
      await page.goto(s.path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(900); // let the pencil stroke finish
      if (s.prep) await s.prep(page);
      await page.screenshot({ path: `${DIR}/${s.name}-${scheme}.png`, fullPage: false });
      await page.screenshot({ path: `${DIR}/${s.name}-${scheme}-full.png`, fullPage: true });
    });
  }
}
