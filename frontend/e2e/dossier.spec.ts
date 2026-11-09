import { expect, test } from "@playwright/test";
import { json, mockApi, watchErrors } from "./mock";

test("Golden path: Today, Dig in, the ledger, a citation, the quote on its page", async ({ page }) => {
  const errors = watchErrors(page);
  await mockApi(page, { digest: () => "digest-7d.json" }); // BAJFINANCE reported this week
  await page.goto("/");
  const card = page.locator('[data-story^="BAJFINANCE:"]').first();
  await card.getByRole("link", { name: "Dig in" }).click();
  await expect(page).toHaveURL(/\/research\/BAJFINANCE$/);
  await expect(page.getByRole("heading", { name: "Promise ledger" })).toBeVisible();

  // open the chip whose page the source fixture holds; its quote must come up highlighted
  const src = json("source-BAJFINANCE.json");
  const source = json("dossier-BAJFINANCE.json").sources.find((s: any) => s.id === src.citation.source_id);
  const month = source.title.match(/\(([A-Za-z]+ \d{4})\)/)?.[1];
  await page
    .getByRole("button", { name: new RegExp(`^${source.quarter} call( \\(${month}\\))?, p\\. ${src.citation.page}$`) })
    .first()
    .click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  await expect(sheet.locator("mark")).toBeInViewport();
  await sheet.getByRole("button", { name: "Close" }).click();
  await expect(sheet).toBeHidden();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("A lender's dossier reads as a lender's", async ({ page }) => {
  await mockApi(page);
  await page.goto("/research/HDFCBANK");
  await expect(page.getByText("Financing margin", { exact: true })).toBeVisible();
});
