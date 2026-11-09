// Screenshots for design review: SCREENS=<dir> npx playwright test e2e/screens.spec.ts
import { test } from "@playwright/test";
import { mockApi } from "./mock";

const DIR = process.env.SCREENS;
test.skip(!DIR, "set SCREENS=<dir> to capture");

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
