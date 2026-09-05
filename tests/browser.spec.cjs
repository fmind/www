const { test, expect } = require("playwright/test");
const { setTimeout: delay } = require("node:timers/promises");

const calculator = "/sites/llm-self-hosting/";

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => {
    throw error;
  });
});

test("published pages render without overflow, missing images, or external assets", async ({ page, request, baseURL }) => {
  test.setTimeout(120000);
  const profile = await (await request.get("/api/profile")).json();
  const paths = [
    "/",
    "/articles/",
    "/sites/",
    calculator,
    ...profile.articles.map((article) => new URL(article.url).pathname),
  ];
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
