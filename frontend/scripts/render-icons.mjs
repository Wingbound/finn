// Renders public/icons/*.svg to the PNG sizes the manifest and iOS need.
// Run: node scripts/render-icons.mjs
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const jobs = [
  ["icon.svg", "icon-192.png", 192],
  ["icon.svg", "icon-512.png", 512],
  ["icon-maskable.svg", "icon-maskable-512.png", 512],
  ["icon-maskable.svg", "apple-touch-icon.png", 180],
];

const browser = await chromium.launch();
const page = await browser.newPage();
for (const [src, out, size] of jobs) {
  const svg = await readFile(new URL(`../public/icons/${src}`, import.meta.url), "utf8");
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(
    `<html><body style="margin:0;background:transparent">${svg.replace("<svg ", `<svg width="${size}" height="${size}" `)}</body></html>`,
  );
  await page.screenshot({ path: fileURLToPath(new URL(`../public/icons/${out}`, import.meta.url)), omitBackground: true });
  console.log(out);
}
await browser.close();
