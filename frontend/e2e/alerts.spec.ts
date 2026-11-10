import { expect, test } from "@playwright/test";
import { json, mockApi, watchErrors } from "./mock";

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

test("Alerts: a filing alert opens its story in Today, on the alert log's own window", async ({ page }) => {
  const bodies: any[] = [];
  await mockApi(page, {
    digest: (b) => (b.start ? "digest-7d.json" : "digest-24h.json"),
    onRequest: (path, body) => path === "/digest" && bodies.push(body),
  });
  await page.goto("/alerts");
  const link = page.locator('a[href^="/#story-"]').first();
  const href = (await link.getAttribute("href")) as string;
  const id = decodeURIComponent(href.replace("/#story-", ""));
  await link.click();
  const end = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" }).format(
    new Date(json("alerts.json").window.end),
  );
  await expect(page.getByRole("radio", { name: new RegExp(`to ${end}$`) })).toHaveAttribute("aria-checked", "true");
  await expect.poll(() => bodies.at(-1)?.start).toBe(json("alerts.json").window.start);
  await expect(page.locator(`[data-story="${id}"]`)).toBeInViewport();
});

test("Alerts: a failed refresh after saving rules says so", async ({ page }) => {
  await mockApi(page);
  await page.goto("/alerts");
  await expect(page.getByRole("heading", { name: /alerts this week/ })).toBeVisible();
  await page.route("http://api.finn.test/alerts", (r) => r.abort("connectionrefused"));
  await page.getByRole("button", { name: "Edit rules" }).click();
  await page.getByLabel("Volume multiple", { exact: true }).fill("1");
  await page.getByRole("button", { name: "Save rules" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Couldn.t reach FINN/ })).toBeVisible();
});
