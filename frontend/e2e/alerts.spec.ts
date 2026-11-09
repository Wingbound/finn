import { expect, test } from "@playwright/test";
import { mockApi, watchErrors } from "./mock";

test("Alerts: lowering the volume rule is saved and sent with the next request", async ({ page }) => {
  const errors = watchErrors(page);
  const bodies: any[] = [];
  await mockApi(page, { onRequest: (path, body) => path === "/alerts" && bodies.push(body) });
  await page.goto("/alerts");
  await expect(page.getByRole("heading", { name: /alerts this week/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /20-day close/ }).first()).toBeVisible();
  expect(bodies[0]).toMatchObject({ volume_multiple: 2 });

  await page.getByRole("button", { name: "Edit rules" }).click();
  await page.getByLabel("Volume multiple", { exact: true }).fill("1");
  await page.getByRole("button", { name: "Save rules" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Rules saved" })).toBeVisible();
  await expect.poll(() => bodies.at(-1)?.volume_multiple).toBe(1);

  await page.reload();
  await expect.poll(() => bodies.at(-1)?.volume_multiple).toBe(1);
  expect(errors).toEqual([]);
});

test("Alerts: a filing alert opens its story in Today's 7-day view", async ({ page }) => {
  await mockApi(page, { digest: (b) => (b.hours === 168 ? "digest-7d.json" : "digest-24h.json") });
  await page.goto("/alerts");
  const link = page.locator('a[href^="/#story-"]').first();
  const href = (await link.getAttribute("href")) as string;
  const id = decodeURIComponent(href.replace("/#story-", ""));
  await link.click();
  await expect(page.getByRole("radio", { name: "7 days" })).toHaveAttribute("aria-checked", "true");
  const card = page.locator(`[data-story="${id}"]`);
  await expect(card).toBeInViewport();
});
