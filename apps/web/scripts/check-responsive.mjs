import { chromium } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";
const widths = [390, 768, 1024, 1440];
const schoolPath =
  process.env.PHILFACILITIES_E2E_SCHOOL_PATH ??
  "/facilities/mulanay-central-elementary-school-osm";
const paths = [
  "/",
  "/directory",
  "/map",
  schoolPath,
  "/data",
  "/data/dictionary",
  "/api",
  "/status",
];

const browser = await chromium.launch();
let failures = 0;

try {
  for (const width of widths) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();

    for (const path of paths) {
      await page.goto(new URL(path, baseURL).toString(), { waitUntil: "load" });
      const metrics = await page.evaluate(() => {
        const header = document.querySelector("header");
        const headerBar = header?.firstElementChild;
        return {
          headerHeight: headerBar?.getBoundingClientRect().height,
          innerWidth: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
        };
      });

      const ok = metrics.scrollWidth <= metrics.innerWidth;
      if (!ok) failures += 1;
      console.log(
        `${ok ? "ok" : "OVERFLOW"} ${width}px ${path} scrollWidth=${metrics.scrollWidth} header=${metrics.headerHeight}px`,
      );
    }

    await context.close();
  }
} finally {
  await browser.close();
}

if (failures > 0) {
  console.error(`${failures} responsive overflow check(s) failed.`);
  process.exitCode = 1;
} else {
  console.log(`All ${widths.length * paths.length} responsive overflow checks passed.`);
}
