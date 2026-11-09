import { expect, test } from "@playwright/test";

test.skip(!process.env.LIVE_URL, "set LIVE_URL to run against the deployed site");

function watchErrors(page: import("@playwright/test").Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(`${m.text()} ${m.location().url ?? ""}`));
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

test("Today, Alerts and Research load with live data", async ({ page }) => {
  const errors = watchErrors(page);
  const t0 = Date.now();
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  console.log(`Today first heading after ${Date.now() - t0} ms: "${await page.getByRole("heading", { level: 1 }).textContent()}"`);
  await page.getByRole("link", { name: "Alerts" }).click();
  await expect(page.getByRole("img", { name: /20-day close/ }).first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: "Research" }).click();
  await expect(page.getByRole("link", { name: /Persistent Systems/ })).toBeVisible({ timeout: 30_000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  expect(errors.filter((e) => !e.includes("favicon"))).toEqual([]);
});

test("A dossier citation opens its page with the quote highlighted", async ({ page }) => {
  await page.goto("/research/PERSISTENT");
  await expect(page.getByRole("heading", { name: "Promise ledger" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /call, p\. \d+$/ }).first().click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.locator("mark")).toBeInViewport({ timeout: 20_000 });
});

test("A live build through the UI ends on the dossier", async ({ page }) => {
  const sym = process.env.LIVE_BUILD;
  test.skip(!sym, "set LIVE_BUILD=SYMBOL to spend one build");
  const t0 = Date.now();
  const lines: string[] = [];
  page.on("console", (m) => lines.push(m.text()));
  await page.goto(`/research/${sym}?build=1`);
  const failed = page.getByRole("alert").filter({ hasText: /stopped|failed|Couldn|not found|timed out/i });
  await expect(page.getByRole("heading", { name: "Promise ledger" }).or(failed)).toBeVisible({ timeout: 220_000 });
  const ok = await page.getByRole("heading", { name: "Promise ledger" }).isVisible();
  console.log(`build of ${sym}: ${ok ? "dossier shown" : "stopped"} after ${Math.round((Date.now() - t0) / 1000)} s`);
  if (!ok) console.log(await failed.textContent());
  expect(ok).toBe(true);
});

test("The API is seeded, allows exactly this site, and says how fast it answered", async ({ request }) => {
  const api = process.env.LIVE_API;
  test.skip(!api, "set LIVE_API to the API's URL");
  const t0 = Date.now();
  const res = await request.get(`${api}/health`);
  const ms = Date.now() - t0;
  const body = await res.json();
  console.log(`/health answered in ${ms} ms (a cold start if this instance was idle)`);
  expect(res.ok()).toBe(true);
  expect(body.seeded).toBe(true);
  expect(body.cors).toEqual([new URL(process.env.LIVE_URL as string).origin]);
  expect(body.cors_problems).toEqual([]);
  expect(body.ok).toBe(true);
});
