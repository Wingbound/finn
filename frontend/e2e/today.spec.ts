import { expect, test } from "@playwright/test";
import { fixture, headlineFor, json, mockApi, watchErrors } from "./mock";

test("Today: change window, see why a story ranks, open what FINN set aside", async ({ page }) => {
  const errors = watchErrors(page);
  const bodies: any[] = [];
  await mockApi(page, {
    digest: (b) => (b.hours === 168 ? "digest-7d.json" : "digest-24h.json"),
    onRequest: (path, body) => {
      if (path === "/digest") bodies.push(body);
    },
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(headlineFor("digest-24h.json"));
  expect(bodies[0]).toMatchObject({ hours: 24, floor: "important" });
  expect(bodies[0].subscribed).toContain("results");

  await page.getByRole("radio", { name: "7 days" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(headlineFor("digest-7d.json"));
  expect(bodies.at(-1)).toMatchObject({ hours: 168 });

  const first = page.getByRole("article").first();
  await first.getByRole("button", { name: "Why it’s here" }).click();
  await expect(first.getByText(/^Score \d+:/)).toBeVisible();

  await page.getByRole("button", { name: /routine filings set aside/ }).click();
  await expect(page.getByText("You’re caught up.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Hide what FINN set aside/ })).toHaveAttribute("aria-expanded", "true");

  // the window choice survives a reload (stored on the device)
  await page.reload();
  await expect(page.getByRole("radio", { name: "7 days" })).toHaveAttribute("aria-checked", "true");
  expect(errors).toEqual([]);
});

test("Today: an empty window says how old the newest filing is", async ({ page }) => {
  await mockApi(page, { digest: () => "digest-empty.json" });
  await page.goto("/");
  await expect(page.getByText("Nothing new in the last 24 hours.")).toBeVisible();
  await expect(page.getByText(/^Newest filing: \d{1,2} [A-Z][a-z]{2}, \d{2}:\d{2}\.$/)).toBeVisible();
});

test("Today: an unreachable server offers a retry", async ({ page }) => {
  await page.route("http://api.finn.test/**", (r) => r.abort("connectionrefused"));
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Couldn’t" }).or(page.getByRole("alert").filter({ hasText: "Couldn't" }))).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("Today: a failed refresh after a window change says so above the older stories", async ({ page }) => {
  await mockApi(page, { digest: () => "digest-24h.json" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(headlineFor("digest-24h.json"));
  await page.route("http://api.finn.test/digest", (r) => r.abort("connectionrefused"));
  await page.getByRole("radio", { name: "7 days" }).click();
  const alert = page.getByRole("alert").filter({ hasText: /Couldn.t reach FINN/ });
  await expect(alert).toBeVisible();
  await expect(alert).toContainText("still showing the previous window");
});

test("Today: a link to a routine story opens the drawer at it (final review I5)", async ({ page }) => {
  await mockApi(page, { digest: () => "digest-24h.json" });
  const routine = Object.values(json("digest-24h.json").routine as Record<string, { id: string }[]>).flat();
  const id = routine[0]!.id;
  await page.goto(`/#story-${encodeURIComponent(id)}`);
  await expect(page.locator(`[id="story-${id}"]`)).toBeInViewport();
});

test("Today: a link to a story outside the window says so (final review I5)", async ({ page }) => {
  await mockApi(page, { digest: () => "digest-24h.json" });
  await page.goto("/#story-NOPE%3Aresults%3A1");
  await expect(page.getByText("That story is outside this window.")).toBeVisible();
});

test("Today: a quiet 24 hours points at what the last 7 days hold (Plan 8)", async ({ page }) => {
  const errors = watchErrors(page);
  await mockApi(page, { digest: (b) => (b.hours === 168 ? "digest-7d.json" : "digest-quiet.json") });
  await page.goto("/");
  await expect(page.getByText("Quiet 24 hours.")).toBeVisible();
  const n = json("digest-7d.json").stories.length;
  await expect(page.getByText(`Over the last 7 days, ${n} things mattered.`)).toBeVisible();
  await page.getByRole("button", { name: "Show 7 days" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(headlineFor("digest-7d.json"));
  await expect(page.getByRole("radio", { name: "7 days" })).toHaveAttribute("aria-checked", "true");
  expect(errors).toEqual([]);
});

test("Today: an update in flight doesn't move the stories (Plan 8)", async ({ page }) => {
  await mockApi(page, { digest: () => "digest-7d.json" });
  await page.goto("/");
  const first = page.getByRole("article").first();
  await expect(first).toBeVisible();
  const before = (await first.boundingBox())?.y;
  await page.route("**/digest", async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.fulfill({ status: 200, contentType: "application/json", body: fixture("digest-7d.json") });
  });
  await page.getByRole("radio", { name: "3 days" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Updating" })).toBeAttached();
  expect((await first.boundingBox())?.y).toBe(before);
});
