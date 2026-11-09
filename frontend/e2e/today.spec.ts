import { expect, test } from "@playwright/test";
import { mockApi, watchErrors } from "./mock";

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
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("7 things matter");
  expect(bodies[0]).toMatchObject({ hours: 24, floor: "important" });
  expect(bodies[0].subscribed).toContain("results");

  await page.getByRole("radio", { name: "7 days" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("27 things matter");
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
  await expect(page.getByText(/Newest filing: 7 Nov, 16:58/)).toBeVisible();
});

test("Today: an unreachable server offers a retry", async ({ page }) => {
  await page.route("http://api.finn.test/**", (r) => r.abort("connectionrefused"));
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Couldn’t" }).or(page.getByRole("alert").filter({ hasText: "Couldn't" }))).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});
