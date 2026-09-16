const { test, expect } = require("playwright/test");

test("portfolio and contact pages render and reflow", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const path of ["/", "/connect", "/scan", "/privacy"]) {
    const response = await page.goto(path);
    expect(response.status()).toBe(200);
    await expect(page.locator("h1")).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const image of await page.locator("img").all()) {
      // Deferred sections can change size when first rendered. Scroll again
      // after layout settles, using the standard API supported by all engines.
      await expect(async () => {
        await image.evaluate((element) => element.scrollIntoView({ block: "center" }));
        await expect(image).toBeInViewport({ timeout: 500 });
      }).toPass({ timeout: 5000 });
      await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0)).toBe(true);
    }
  }
  for (const width of [320, 768, 1024, 1600]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const label of ["Portfolio", "Articles", "Sites"]) {
      await expect(
        page.getByRole("navigation", { name: "Primary navigation" }).getByRole("link", { name: label, exact: true }),
      ).toBeInViewport();
    }
  }
  expect(errors).toEqual([]);
});

test("keyboard section navigation and skip link work", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
  const summary = page.locator("#section-menu summary");
  await summary.focus();
  await page.keyboard.press("Enter");
  await page.getByRole("navigation", { name: "Portfolio sections" }).getByRole("link", {
    name: "Services",
    exact: true,
  }).click();
  await expect(page.locator("#services")).toBeFocused();
  await expect(page.locator("#section-menu")).not.toHaveAttribute("open");
  await summary.focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Escape");
  await expect(summary).toBeFocused();
  await expect(page.locator("#section-menu")).not.toHaveAttribute("open");
});

test("contact download and navigation work without JavaScript", async ({ browser }, testInfo) => {
  const context = await browser.newContext({ ...testInfo.project.use, javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    await page.goto("/connect");
    const downloaded = page.waitForEvent("download");
    await page.getByRole("link", { name: "Save my contact" }).click();
    const download = await downloaded;
    expect(await download.failure()).toBeNull();
    expect(download.suggestedFilename()).toBe("mederic-hurier.vcf");
    const response = await context.request.get("/connect.vcf");
    expect(response.status()).toBe(200);
    expect(await response.text()).toContain("BEGIN:VCARD\r\nVERSION:3.0");
    await page.getByRole("link", { name: "Go to my website" }).click();
    await page.locator("#section-menu summary").click();
    await page.getByRole("navigation", { name: "Portfolio sections" }).getByRole("link", {
      name: "Services",
      exact: true,
    }).click();
    await expect(page).toHaveURL(/#services$/);
    await expect(page.locator("#services")).toBeInViewport();
  } finally {
    await context.close();
  }
});

test("off-screen archive cards remain reachable by keyboard", async ({ page }) => {
  await page.goto("/articles/");
  const lastTitle = page.locator(".article-index article h3 a").last();
  const destination = await lastTitle.getAttribute("href");
  await lastTitle.focus();
  await expect(lastTitle).toBeFocused();
  await expect(lastTitle).toBeInViewport();
  const card = page.locator(".article-index article").last();
  const bounds = await card.boundingBox();
  const body = await card.locator(".card-body").boundingBox();
  expect(body.y + body.height).toBeLessThanOrEqual(bounds.y + bounds.height);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(destination);
  await expect(page.locator("h1")).toHaveCount(1);
});
