const { test, expect } = require("playwright/test");
const { setTimeout: delay } = require("node:timers/promises");

const calculator = "/sites/llm-self-hosting/";

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => {
    throw error;
  });
});

test("published pages render without overflow, missing images, or external assets", async ({ page, request, baseURL }) => {
  // A remote full-sitemap crawl needs headroom for network variance while each
  // navigation and image assertion remains independently bounded below.
  test.setTimeout(360000);
  const profile = await (await request.get("/api/profile")).json();
  const paths = [
    "/",
    "/articles/",
    "/sites/",
    calculator,
    ...profile.articles.map((article) => new URL(article.url).pathname),
  ];
  const sitemapResponse = await request.get("/sitemap.xml");
  expect(sitemapResponse.status()).toBe(200);
  const sitemapPaths = [...(await sitemapResponse.text()).matchAll(/<loc>([^<]+)<\/loc>/g)]
    .map(([, location]) => new URL(location).pathname);
  // Discovery must stay closed over the same hosted pages the browser crawls.
  expect([...new Set(sitemapPaths)].sort()).toEqual([...new Set(paths)].sort());
  expect(sitemapPaths).toHaveLength(paths.length);
  const external = [];
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== new URL(baseURL).origin) external.push(request.url());
  });
  for (const path of paths) {
    const response = await page.goto(path);
    expect(response.status(), path).toBe(200);
    await expect(page.locator("h1")).toHaveCount(1);
    const geometry = await page.evaluate(() => ({
      width: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(geometry.content, path).toBeLessThanOrEqual(geometry.width + 1);
    for (const image of await page.locator("img").all()) {
      await image.scrollIntoViewIfNeeded();
      await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0)).toBe(true);
    }
  }
  expect(external).toEqual([]);
});

test("cost chart labels remain legible and contained at the tablet breakpoint", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 900 });
  await page.goto(calculator);

  const geometry = await page.locator("[data-cost-explorer] svg").evaluate((svg) => {
    const chart = svg.getBoundingClientRect();
    const labels = [...svg.querySelectorAll("text")]
      .filter((label) => getComputedStyle(label).display !== "none")
      .map((label) => {
        const bounds = label.getBoundingClientRect();
        return {
          label: label.textContent.trim(),
          height: bounds.height,
          left: bounds.left,
          right: bounds.right,
          top: bounds.top,
          bottom: bounds.bottom,
        };
      });
    const overlaps = [];
    for (let left = 0; left < labels.length; left += 1) {
      for (let right = left + 1; right < labels.length; right += 1) {
        const first = labels[left];
        const second = labels[right];
        if (
          first.left < second.right && first.right > second.left
          && first.top < second.bottom && first.bottom > second.top
        ) {
          overlaps.push(`${first.label} / ${second.label}`);
        }
      }
    }
    return {
      chart: { left: chart.left, right: chart.right, top: chart.top, bottom: chart.bottom },
      labels,
      overlaps,
      viewportWidth: document.documentElement.clientWidth,
      contentWidth: document.documentElement.scrollWidth,
    };
  });

  expect(geometry.labels.length).toBeGreaterThan(0);
  expect(geometry.contentWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  expect(geometry.overlaps).toEqual([]);
  for (const label of geometry.labels) {
    expect(label.height, label.label).toBeGreaterThanOrEqual(12);
    expect(label.left, label.label).toBeGreaterThanOrEqual(geometry.chart.left - 1);
    expect(label.right, label.label).toBeLessThanOrEqual(geometry.chart.right + 1);
    expect(label.top, label.label).toBeGreaterThanOrEqual(geometry.chart.top - 1);
    expect(label.bottom, label.label).toBeLessThanOrEqual(geometry.chart.bottom + 1);
  }
});

test("theme and menu remain usable when storage is blocked", async ({ page }) => {
  await page.addInitScript(() =>
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new DOMException("Storage blocked", "SecurityError");
      },
    })
  );
  await page.goto("/");
  const initial = await page.locator("html").getAttribute("data-theme");
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", initial === "dark" ? "light" : "dark");
  await page.locator("#menu-toggle").click();
  await expect(page.locator("#mobile-menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator("#mobile-menu")).toBeHidden();
  await expect(page.locator("#menu-toggle")).toBeFocused();
});

test("late font downloads keep the article layout stable", async ({ page }) => {
  await page.addInitScript(() => {
    window.layoutShifts = [];
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) window.layoutShifts.push(entry.value);
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  await page.route("**/static/fonts/*.woff2", async (route) => {
    // A cold connection delivers fonts after the initial font-display window.
    await delay(600);
    await route.continue();
  });
  await page.goto("/articles/agentgateway-vs-litellm/");
  await page.evaluate(() => document.fonts.ready);
  const fontLoads = await page.evaluate(async () =>
    Promise.all(
      ["Inter", "Outfit"].map(async (family) => {
        const faces = await document.fonts.load(`16px "${family}"`);
        return { family, statuses: faces.map((face) => face.status) };
      }),
    )
  );
  for (const { family, statuses } of fontLoads) {
    expect(statuses, `${family} font face was not loaded`).not.toHaveLength(0);
    expect(statuses, `${family} font face was not ready`).toEqual(statuses.map(() => "loaded"));
  }
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const shift = await page.evaluate(() => window.layoutShifts.reduce((sum, value) => sum + value, 0));
  expect(shift).toBeLessThan(0.001);
});

test("theme choice persists and keyboard skip link reaches main content", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
  await page.locator("#theme-toggle").click();
  const theme = await page.locator("html").getAttribute("data-theme");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
});

test("a full storage quota does not prevent changing the theme", async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException("Storage full", "QuotaExceededError");
    };
  });
  await page.goto("/");
  const initial = await page.locator("html").getAttribute("data-theme");
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", initial === "dark" ? "light" : "dark");
});

test("calculator updates preserve focus, disclosures, and shareable values", async ({ page }) => {
  await page.goto(calculator);
  await page.locator("#quality-settings > summary").click();
  await page.locator("#requests").fill("234");
  await page.locator("#requests").press("Enter");
  await expect(page.locator("[data-update-status]")).toHaveText("Comparison updated.");
  await expect(page.locator("#requests")).toHaveValue("234");
  await expect(page.locator("#requests")).toBeFocused();
  await expect(page.locator("#quality-settings")).toHaveAttribute("open", "");
  expect(new URL(page.url()).searchParams.get("requests")).toBe("234");
  await page.locator("#preset-single-job").click();
  await expect(page.locator("#requests")).toHaveValue("100");
  await expect(page.locator("#days")).toHaveValue("1");
  await page.locator("#cost-volume").focus();
  await page.locator("#cost-volume").press("End");
  const scenario = await page.locator("#apply-demand").getAttribute("href");
  await page.locator("#apply-demand").click();
  await expect(page).toHaveURL(new URL(scenario, page.url()).href);
  await expect(page.locator("#apply-demand")).toBeFocused();
});

test("calculator reports network failure and recovers on retry", async ({ page }) => {
  await page.goto(calculator);
  await page.route("**/sites/llm-self-hosting/?*", (route) => route.abort("failed"));
  await page.locator("#update-comparison").click();
  await expect(page.getByRole("alert")).toContainText("Could not update");
  await expect(page.locator("[data-hosting-calculator]")).not.toHaveAttribute("aria-busy", "true");
  await page.unroute("**/sites/llm-self-hosting/?*");
  await page.locator("#update-comparison").click();
  await expect(page.locator("[data-update-status]")).toHaveText("Comparison updated.");
});

test("invalid optional inputs open their disclosure before receiving focus", async ({ page }) => {
  await page.goto(calculator);
  await page.locator("#latency-settings > summary").click();
  await page.locator("#measured-first").fill("4000");
  await page.locator("#latency-settings > summary").click();
  await page.locator("#update-comparison").click();
  await expect(page.locator("#latency-settings")).toHaveAttribute("open", "");
  await expect(page.locator("#measured-first")).toBeFocused();
});

test("calculator and article search work without JavaScript", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL });
  const page = await context.newPage();
  await page.goto(calculator);
  await page.locator("#requests").fill("345");
  await page.locator("#update-comparison").click();
  await expect(page.locator("#requests")).toHaveValue("345");
  expect(new URL(page.url()).searchParams.get("requests")).toBe("345");
  await page.goto("/articles/?q=agents");
  await expect(page.locator("main")).toContainText("agents");
  await context.close();
});
