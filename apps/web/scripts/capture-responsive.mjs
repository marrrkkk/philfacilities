import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const outputDirectory =
  process.env.SCREENSHOT_DIR ??
  path.resolve(scriptDirectory, "../../../docs/design-audit/implementation");

const captures = [
  { name: "home", path: "/", width: 390, height: 844 },
  { name: "home", path: "/", width: 768, height: 1024 },
  { name: "home", path: "/", width: 1024, height: 768 },
  { name: "home", path: "/", width: 1440, height: 900 },
  { name: "home", path: "/", width: 1920, height: 1080 },
  { name: "directory", path: "/directory", width: 390, height: 844 },
  { name: "directory", path: "/directory", width: 1440, height: 900 },
  { name: "map", path: "/map", width: 390, height: 844 },
  { name: "map", path: "/map", width: 1440, height: 900 },
];

await mkdir(outputDirectory, { recursive: true });

const browser = await chromium.launch();

try {
  for (const capture of captures) {
    const context = await browser.newContext({
      colorScheme: "light",
      deviceScaleFactor: 1,
      reducedMotion: "reduce",
      viewport: { width: capture.width, height: capture.height },
    });
    const page = await context.newPage();
    const url = new URL(capture.path, baseURL).toString();
    const filename = `${capture.name}-${capture.width}x${capture.height}.png`;

    await page.goto(url, { waitUntil: "load" });

    if (capture.name === "map") {
      await page.locator("canvas.maplibregl-canvas").waitFor();
      // Wait for the bounded viewport query, not just the canvas. The mobile layout
      // hides the results aside, so "Updating" is the only visible readiness text there.
      await page.getByText(/mapped records in view/).waitFor({ timeout: 20_000 });
      await page.waitForTimeout(500);
    } else {
      await page.getByRole("heading", { level: 1 }).first().waitFor();
      await page.waitForLoadState("networkidle");
    }

    await page.screenshot({
      path: path.join(outputDirectory, filename),
      fullPage: true,
    });
    console.log(`${filename} ${url}`);
    await context.close();
  }
} finally {
  await browser.close();
}
