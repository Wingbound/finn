import { expect, test } from "@playwright/test";
import { API } from "../playwright.config";
import { headlineFor, mockApi } from "./mock";

test.use({ serviceWorkers: "allow" });

test("after one online visit, Today still opens when FINN's server is unreachable", async ({ context, page }) => {
  await mockApi(context, { digest: () => "digest-24h.json" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(headlineFor("digest-24h.json"));
  await page.waitForFunction(() => navigator.serviceWorker?.controller !== null || false, null, { timeout: 10_000 }).catch(() => {});
  await page.reload(); // now controlled by the worker, which caches what it fetches
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(headlineFor("digest-24h.json"));
  expect(await page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);

  await context.unrouteAll({ behavior: "ignoreErrors" });
  await context.route(`${API}/**`, (r) => r.abort("internetdisconnected"));
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(headlineFor("digest-24h.json"));
  await expect(page.getByRole("status").filter({ hasText: /Offline/ })).toBeVisible();
});

test("the app is installable: manifest with icons", async ({ request }) => {
  const res = await request.get("/manifest.webmanifest");
  expect(res.ok()).toBe(true);
  const m = await res.json();
  expect(m.display).toBe("standalone");
  expect(m.icons.map((i: { sizes: string }) => i.sizes)).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  for (const i of m.icons) expect((await request.get(i.src)).ok()).toBe(true);
});
