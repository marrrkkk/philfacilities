import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

async function readHeaderState(page: Page) {
  return page.evaluate(() => {
    const header = document.querySelector("header");
    const headerBar = header?.firstElementChild;
    const nav = document.querySelector('nav[aria-label="Main navigation"]');
    const menu = header?.querySelector("button[aria-controls]");
    const browse = [...document.querySelectorAll("header a")].find(
      (element) => element.textContent?.trim() === "Browse facilities",
    );
    return {
      browseDisplay: browse ? getComputedStyle(browse).display : null,
      headerBackground: header ? getComputedStyle(header).backgroundColor : null,
      headerBarHeight: headerBar?.getBoundingClientRect().height,
      menuDisplay: menu ? getComputedStyle(menu).display : null,
      navDisplay: nav ? getComputedStyle(nav).display : null,
    };
  });
}

async function gotoHydrated(page: Page, path: string) {
  await page.goto(path);
  // Hydration reconciles uncontrolled inputs to defaultValue and can discard
  // keystrokes typed before the client bundle is interactive.
  await page.waitForFunction(() => document.documentElement.dataset.hydrated === "true");
}

async function expectMeasuredFocusRing(locator: Locator) {
  const outline = await locator.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      color: style.outlineColor,
      offset: style.outlineOffset,
      style: style.outlineStyle,
      width: style.outlineWidth,
    };
  });

  expect(outline.style).toBe("solid");
  expect(outline.width).toBe("3px");
  expect(outline.color).toBe("rgb(255, 207, 74)");
  expect(outline.offset).toBe("3px");
}

test.describe("directory", () => {
  test("search submits from the keyboard", async ({ page }) => {
    await gotoHydrated(page, "/directory");
    await page.locator("#filter-q").focus();
    await page.keyboard.type("Mulanay Central Elementary");
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/[?&]q=Mulanay(?:\+|%20)Central(?:\+|%20)Elementary/);
    await expect(page.getByRole("heading", { name: "1 matching records" })).toBeVisible();
  });

  test("search narrows results and preserves the query in the URL", async ({ page }) => {
    await gotoHydrated(page, "/directory");
    await expect(page.getByRole("heading", { name: /matching records/i })).toBeVisible();

    await page.locator("#filter-q").fill("Mulanay Central Elementary");
    await page.getByRole("button", { name: "Apply filters" }).click();

    await expect(page).toHaveURL(/[?&]q=Mulanay(?:\+|%20)Central(?:\+|%20)Elementary/);
    await expect(page.getByRole("heading", { name: "1 matching records" })).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Mulanay Central Elementary School", exact: true }),
    ).toBeVisible();
    await expect(
      page.locator("article").getByText(/Map geocoded/).first(),
    ).toBeVisible();
  });

  test("missing coordinates stay labelled as unknown", async ({ page }) => {
    await page.goto("/directory?has_coordinates=false");
    await expect(page.getByText(/matching records/i)).toBeVisible();
    await expect(page.getByText("Coordinates unknown").first()).toBeVisible();
  });

  test("compact search preserves active filters", async ({ page }) => {
    await gotoHydrated(
      page,
      "/directory?type=school&province_code=0405600000&source=osm",
    );
    const search = page.getByRole("search");
    await search.getByRole("searchbox").fill("Mulanay Central Elementary");
    await search.getByRole("button", { name: "Search" }).click();

    await expect(page).toHaveURL(/[?&]q=Mulanay(?:\+|%20)Central(?:\+|%20)Elementary/);
    await expect(page).toHaveURL(/type=school/);
    await expect(page).toHaveURL(/province_code=0405600000/);
    await expect(page).toHaveURL(/source=osm/);
    await expect(page.getByRole("heading", { name: "1 matching records" })).toBeVisible();
  });
});

test.describe("facility profile", () => {
  test("shows provenance, source attribution, and quality caveats", async ({ page }) => {
    await page.goto("/facilities/mulanay-central-elementary-school-osm");

    await expect(
      page.getByRole("heading", { name: "Mulanay Central Elementary School", level: 1 }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Where this information comes from" }),
    ).toBeVisible();
    await expect(page.getByText("HOT-OSM-PHL-EDUCATION-2026-11-15").first()).toBeVisible();
    await expect(page.getByText("© OpenStreetMap contributors, via HOT and BetterGov.PH").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Data quality/i })).toBeVisible();
    await expect(page.getByText("way/313366485", { exact: true }).first()).toBeVisible();
  });

  test("keeps wide tables inside their own scroll region on mobile", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile-chromium", "mobile viewport regression");

    await page.goto("/facilities/mulanay-central-elementary-school-osm");
    await expect(
      page.getByRole("heading", { name: "Mulanay Central Elementary School", level: 1 }),
    ).toBeVisible();

    const viewport = page.viewportSize();
    const metrics = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(metrics.innerWidth).toBe(viewport?.width);
    expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.innerWidth);

    const sourceRegion = page.getByRole("region", { name: "Source evidence" });
    await sourceRegion.scrollIntoViewIfNeeded();
    const table = await sourceRegion.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
    expect(table.scrollWidth).toBeGreaterThan(table.clientWidth);
  });
});

test.describe("map", () => {
  test("loads the MapLibre worker and always provides an equivalent text result list", async ({
    page,
  }, testInfo) => {
    const cspViolations: string[] = [];
    page.on("console", (message) => {
      if (
        message.type() === "error" &&
        /content security policy|refused to (load|execute|apply)/i.test(message.text())
      ) {
        cspViolations.push(message.text());
      }
    });
    const workerResponse = page.waitForResponse(
      (response) =>
        response.url().includes("/vendor/maplibre-gl/") && response.status() === 200,
    );

    await page.goto("/map?q=Bantug na Munti Primary School");
    await workerResponse;
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
    await expect(
      page.locator(".maplibregl-ctrl-attrib").getByRole("link", { name: "OpenStreetMap" }),
    ).toBeVisible();

    if (testInfo.project.name === "mobile-chromium") {
      await page.getByRole("button", { name: /^List \(/ }).click();
    }

    const results = page.getByRole("complementary", { name: "Map results list" });
    await expect(results).toBeVisible();
    await expect(results.getByRole("heading", { name: "Map results" })).toBeVisible();
    await expect(
      results.getByRole("button", { name: /Bantug na Munti Primary School/ }).first(),
    ).toBeVisible({
      timeout: 20_000,
    });
    await expect(results.getByText(/The same records are listed here/)).toBeVisible();
    expect(cspViolations).toEqual([]);
  });

  test("keeps the text result list when basemap tiles fail", async ({ page }, testInfo) => {
    await page.route("**/tile.openstreetmap.org/**", (route) => route.abort());

    await page.goto("/map?q=Bantug na Munti Primary School");
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
    await expect(page.getByRole("alert").filter({ hasText: /basemap could not load/i })).toBeVisible({
      timeout: 20_000,
    });

    if (testInfo.project.name === "mobile-chromium") {
      await page.getByRole("button", { name: /^List \(/ }).click();
    }

    const results = page.getByRole("complementary", { name: "Map results list" });
    await expect(results).toBeVisible();
    await expect(
      results.getByRole("button", { name: /Bantug na Munti Primary School/ }).first(),
    ).toBeVisible({
      timeout: 20_000,
    });
  });

  test("carries directory filters into the map instead of undefined values", async ({
    page,
  }, testInfo) => {
    await page.goto(
      "/directory?type=school&location_precision=map_geocoded&province_code=0304900000&updated_since=2026-11-01&q=Bantug+na+Munti+Primary+School",
    );
    const mapLink = page.getByRole("link", { name: "View on map" });
    const href = await mapLink.getAttribute("href");
    expect(href).toBeTruthy();

    const params = new URL(href ?? "/map", "http://localhost").searchParams;
    expect(params.get("type")).toBe("school");
    expect(params.get("location_precision")).toBe("map_geocoded");
    expect(params.get("province_code")).toBe("0304900000");
    expect(params.get("updated_since")).toBe("2026-11-01");
    expect(params.get("q")).toBe("Bantug na Munti Primary School");
    expect([...params.values()]).not.toContain("undefined");

    await mapLink.click();
    await expect(page).toHaveURL(/type=school/);
    await expect(page).toHaveURL(/location_precision=map_geocoded/);
    await expect(page).toHaveURL(/province_code=0304900000/);
    await expect(page).toHaveURL(/updated_since=2026-11-01/);

    if (testInfo.project.name === "mobile-chromium") {
      await page.getByRole("button", { name: /^List \(/ }).click();
    }

    const results = page.getByRole("complementary", { name: "Map results list" });
    await expect(
      results.getByRole("button", { name: /Bantug na Munti Primary School/ }).first(),
    ).toBeVisible({
      timeout: 20_000,
    });
    await expect(results.getByRole("button", { name: /Health/ })).toHaveCount(0);
  });
});

test.describe("data dictionary", () => {
  test("documents missing-value, precision, and identity review semantics", async ({ page }) => {
    await page.goto("/data/dictionary");
    await expect(
      page.getByRole("heading", {
        name: "Every field, its meaning, and what the data cannot tell you.",
        level: 1,
      }),
    ).toBeVisible();
    await expect(page.getByText(/Missing is not zero, false, or inactive/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Coordinate precision" })).toBeVisible();
    await expect(page.getByText("barangay_centroid", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Identity matching and review" }),
    ).toBeVisible();
    await expect(page.getByText("merged", { exact: true })).toBeVisible();
    await expect(
      page.getByText(/any remaining synthetic fixtures are labelled/),
    ).toBeVisible();
    await expect(
      page.locator("#main-content").getByRole("link", { name: "Dataset catalogue" }),
    ).toBeVisible();
  });
});

test.describe("status", () => {
  test("shows measured service state and identity review counts", async ({ page }) => {
    await page.goto("/status");
    await expect(page.getByRole("heading", { name: "Service and data status" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Identity review" })).toBeVisible();
    await expect(page.getByText(/pending$/).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Pending candidates JSON" })).toBeVisible();
    await expect(page.getByText(/never merged automatically/)).toBeVisible();
  });
});

test.describe("keyboard access", () => {
  test("skip link moves focus to the main content", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");

    const skipLink = page.getByRole("link", { name: "Skip to main content" });
    await expect(skipLink).toBeFocused();
    await expect(skipLink).toBeInViewport();

    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    expect(new URL(page.url()).hash).toBe("#main-content");
  });

  test("desktop navigation is keyboard reachable and shows the measured focus ring", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop-chromium", "desktop navigation focus test");

    await page.goto("/");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");

    const directory = page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: "Directory" });
    await expect(directory).toBeFocused();
    await expectMeasuredFocusRing(directory);

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/directory$/);
    await expect(page.getByRole("heading", { name: /matching records/i })).toBeVisible();
  });
});

test.describe("design tokens", () => {
  test("keeps the measured header, typography, button, and responsive geometry", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop-chromium", "measured desktop tokens");

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");

    const desktop = await readHeaderState(page);
    expect(desktop.headerBarHeight).toBe(68);
    expect(desktop.headerBackground).toBe("rgba(0, 34, 110, 0.94)");
    expect(desktop.navDisplay).not.toBe("none");
    expect(desktop.menuDisplay).toBe("none");
    expect(desktop.browseDisplay).not.toBe("none");

    const fonts = await page.evaluate(() => {
      const heading = document.querySelector("h1");
      const bodyStyle = getComputedStyle(document.body);
      return {
        bodyFont: bodyStyle.fontFamily,
        headingFont: heading ? getComputedStyle(heading).fontFamily : null,
      };
    });
    expect(fonts.bodyFont).toContain("Archivo");
    expect(fonts.headingFont).toContain("Inter");

    const browse = page.getByRole("link", { name: "Browse facilities" });
    const button = await browse.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        background: style.backgroundColor,
        height: element.getBoundingClientRect().height,
        radius: style.borderRadius,
      };
    });
    expect(button.height).toBe(40);
    expect(button.background).toBe("rgb(252, 209, 22)");
    expect(button.radius).toBe("0px");

    await page.setViewportSize({ width: 390, height: 844 });
    const mobile = await readHeaderState(page);
    expect(mobile.headerBarHeight).toBe(60);
    expect(mobile.navDisplay).toBe("none");
    expect(mobile.menuDisplay).not.toBe("none");
    expect(mobile.browseDisplay).toBe("none");

    await page.setViewportSize({ width: 768, height: 1024 });
    const tablet = await readHeaderState(page);
    expect(tablet.headerBarHeight).toBe(68);
    expect(tablet.navDisplay).toBe("none");
    expect(tablet.menuDisplay).not.toBe("none");
    expect(tablet.browseDisplay).toBe("none");

    await page.setViewportSize({ width: 1024, height: 768 });
    const referenceBreakpoint = await readHeaderState(page);
    expect(referenceBreakpoint.headerBarHeight).toBe(68);
    expect(referenceBreakpoint.navDisplay).toBe("none");
    expect(referenceBreakpoint.menuDisplay).not.toBe("none");
    expect(referenceBreakpoint.browseDisplay).toBe("none");

    await page.setViewportSize({ width: 1025, height: 768 });
    const narrowDesktop = await readHeaderState(page);
    expect(narrowDesktop.headerBarHeight).toBe(68);
    expect(narrowDesktop.navDisplay).not.toBe("none");
    expect(narrowDesktop.menuDisplay).toBe("none");
    expect(narrowDesktop.browseDisplay).not.toBe("none");
  });
});

test.describe("navigation", () => {
  test("mobile menu exposes the same primary destinations and closes on Escape", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile-chromium", "mobile-only navigation behaviour");

    await gotoHydrated(page, "/");
    const menu = page.getByRole("button", { name: "Menu" });
    await expect(menu).toBeVisible();
    await menu.focus();
    await page.keyboard.press("Enter");

    const nav = page.getByRole("navigation", { name: "Mobile navigation" });
    await expect(nav).toBeVisible();
    const directory = nav.getByRole("link", { name: "Directory" });
    await expect(directory).toBeVisible();
    await expect(nav.getByRole("link", { name: "Data & Sources" })).toBeVisible();

    await page.keyboard.press("Tab");
    await expect(directory).toBeFocused();
    await expectMeasuredFocusRing(directory);

    await page.keyboard.press("Escape");
    await expect(nav).toBeHidden();
    await expect(menu).toBeFocused();
  });
});

test.describe("security headers", () => {
  test("serves a nonce-based content security policy", async ({ request }) => {
    const first = await request.get("/");
    expect(first.ok()).toBeTruthy();
    const headers = first.headers();
    const policy = headers["content-security-policy"];
    expect(policy).toContain("default-src 'self'");
    expect(policy).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
    expect(policy).not.toMatch(/script-src[^;]*'unsafe-inline'/);
    expect(policy).toContain("style-src 'self' 'nonce-");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("worker-src 'self' blob:");
    const apiOrigin = new URL(process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8010").origin;
    expect(policy).toContain(`connect-src 'self' ${apiOrigin}`);

    const nonce = /script-src 'self' 'nonce-([^']+)'/.exec(policy ?? "")?.[1];
    expect(nonce).toBeTruthy();
    const html = await first.text();
    const scripts = html.match(/<script\b[^>]*>/g) ?? [];
    expect(scripts.length).toBeGreaterThan(0);
    for (const script of scripts) {
      expect(script).toContain(`nonce="${nonce}"`);
    }

    // A nonce is per response; a cached or reused value would defeat its purpose.
    const second = await request.get("/");
    expect(second.headers()["content-security-policy"]).not.toBe(policy);
  });

  test("baseline browser protections are present", async ({ request }) => {
    const response = await request.get("/");
    expect(response.ok()).toBeTruthy();
    const headers = response.headers();
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["permissions-policy"]).toContain("geolocation=()");
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(headers["x-powered-by"]).toBeUndefined();
  });

  test("public pages do not violate the policy", async ({ page }) => {
    const violations: string[] = [];
    page.on("console", (message) => {
      if (
        message.type() === "error" &&
        /content security policy|refused to (load|execute|apply)/i.test(message.text())
      ) {
        violations.push(message.text());
      }
    });
    page.on("pageerror", (error) => violations.push(error.message));

    for (const path of [
      "/",
      "/directory",
      "/facilities/mulanay-central-elementary-school-osm",
      "/data",
      "/data/dictionary",
      "/api",
      "/sources",
      "/status",
      "/about",
    ]) {
      await page.goto(path, { waitUntil: "load" });
      await page.waitForTimeout(150);
    }

    expect(violations).toEqual([]);
  });
});

test.describe("responsive layout", () => {
  test("public pages keep their content inside the mobile viewport", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile-chromium", "mobile viewport regression");

    for (const path of [
      "/",
      "/directory",
      "/map",
      "/facilities/mulanay-central-elementary-school-osm",
      "/data",
      "/data/dictionary",
      "/api",
      "/status",
    ]) {
      await page.goto(path, { waitUntil: "load" });
      const metrics = await page.evaluate(() => ({
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
      }));
      expect(metrics.scrollWidth, `${path} overflows the viewport`).toBeLessThanOrEqual(
        metrics.innerWidth,
      );
    }
  });
});

test.describe("accessibility", () => {
  for (const path of [
    "/",
    "/directory",
    "/facilities/mulanay-central-elementary-school-osm",
    "/data",
    "/data/dictionary",
    "/api",
    "/status",
  ]) {
    test(`axe finds no serious or critical violations on ${path}`, async ({ page }) => {
      await page.goto(path);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const blocking = results.violations.filter(
        (violation) => violation.impact === "serious" || violation.impact === "critical",
      );
      expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
    });
  }
});
