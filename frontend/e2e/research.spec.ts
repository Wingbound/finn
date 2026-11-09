import { expect, test } from "@playwright/test";
import { mockApi, watchErrors } from "./mock";

test("Research: search a new company, watch it build, land on its dossier", async ({ page }) => {
  const errors = watchErrors(page);
  await mockApi(page);
  await page.goto("/research");
  await expect(page.getByRole("link", { name: /Persistent Systems/ })).toBeVisible();
  await page.getByLabel("Search a company or NSE symbol").fill("pid");
  await page.getByRole("link", { name: /Pidilite Industries.*Build a dossier/ }).click();
  await expect(page).toHaveURL(/\/research\/PIDILITIND$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(errors).toEqual([]);
});

test("Research: a known company opens straight away", async ({ page }) => {
  await mockApi(page);
  await page.goto("/research");
  await page.getByLabel("Search a company or NSE symbol").fill("pers");
  await page.getByRole("link", { name: /Persistent Systems.*Open/ }).click();
  await expect(page).toHaveURL(/\/research\/PERSISTENT$/);
});

test("Research: Dig in on a company with no dossier offers a build", async ({ page }) => {
  await mockApi(page, { missingDossiers: ["TATASTEEL"] });
  await page.goto("/research/TATASTEEL");
  await expect(page.getByRole("button", { name: "Build a dossier" })).toBeVisible();
});
