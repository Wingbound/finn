import { expect, test } from "@playwright/test";
import { mockApi, watchErrors } from "./mock";

for (const [path, tab] of [
  ["/", "Today"],
  ["/alerts", "Alerts"],
  ["/research", "Research"],
] as const) {
  test(`${tab} loads with no console errors and no horizontal scroll`, async ({ page }) => {
    const errors = watchErrors(page);
    await mockApi(page);
    await page.goto(path);
    await expect(page.getByRole("link", { name: tab })).toHaveAttribute("aria-current", "page");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    expect(errors).toEqual([]);
  });
}
