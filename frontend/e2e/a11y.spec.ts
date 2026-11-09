import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mockApi, watchErrors } from "./mock";

const SCREENS = [
  { name: "Today", path: "/", ready: "heading" },
  { name: "Alerts", path: "/alerts", ready: "heading" },
  { name: "Research", path: "/research", ready: "heading" },
  { name: "Dossier", path: "/research/PERSISTENT", ready: "heading" },
  { name: "Lender dossier", path: "/research/HDFCBANK", ready: "heading" },
];

for (const size of [
  { width: 390, height: 844, scheme: "light" as const },
  { width: 360, height: 740, scheme: "light" as const },
  { width: 390, height: 844, scheme: "dark" as const },
]) {
  for (const s of SCREENS) {
    test(`${s.name} at ${size.width}px, ${size.scheme}: no serious a11y issues, no overflow, no console errors`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.emulateMedia({ colorScheme: size.scheme });
      const errors = watchErrors(page);
      await mockApi(page);
      await page.goto(s.path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      const axe = await new AxeBuilder({ page }).analyze();
      const bad = axe.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`);
      expect(bad).toEqual([]);
      expect(errors).toEqual([]);
    });
  }
}

test("sheets pass axe too: rules and a source page", async ({ page }) => {
  await mockApi(page);
  await page.goto("/alerts");
  await page.getByRole("button", { name: "Edit rules" }).click();
  let axe = await new AxeBuilder({ page }).include("dialog[open]").analyze();
  expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);

  await page.goto("/research/PERSISTENT");
  await page.getByRole("button", { name: /call, p\. \d+$/ }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  axe = await new AxeBuilder({ page }).include("dialog[open]").analyze();
  expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
});
