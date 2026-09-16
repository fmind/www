const { test, expect } = require("playwright/test");
const { setTimeout: delay } = require("node:timers/promises");

const calculator = "/sites/llm-self-hosting/";

test("portfolio navigation remains usable without JavaScript", async ({ browser }, testInfo) => {
  const context = await browser.newContext({ ...testInfo.project.use, javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    await page.goto("/");
    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    await page.setViewportSize({ width: 1024, height: 900 });
    await page.locator("#section-menu summary").click();
    await page.getByRole("navigation", { name: "Portfolio sections" }).getByRole("link", {
      name: "Services",
      exact: true,
    }).click();
    await expect(page).toHaveURL(/#services$/);
    await navigation.getByRole("link", { name: "Articles", exact: true }).click();
    await expect(page).toHaveURL(/\/articles\/$/);
    await navigation.getByRole("link", { name: "Sites", exact: true }).click();
    await expect(page).toHaveURL(/\/sites\/$/);
  } finally {
    await context.close();
  }
});

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
    "/connect",
    "/privacy",
    "/agents",
    "/articles/",
    "/sites/",
    calculator,
    ...profile.articles.map((article) => new URL(article.url).pathname),
  ];
  const sitemapResponse = await request.get("/sitemap.xml");
  expect(sitemapResponse.status()).toBe(200);
  const sitemapPaths = [...(await sitemapResponse.text()).matchAll(/<loc>([^<]+)<\/loc>/g)]
    .map(([, location]) => new URL(location).pathname);
  // Discovery must stay closed over the indexable pages.
  expect([...new Set(sitemapPaths)].sort()).toEqual([...new Set(paths)].sort());
  expect(sitemapPaths).toHaveLength(paths.length);
  const external = [];
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== new URL(baseURL).origin) external.push(request.url());
  });
  // The QR display is intentionally noindex but needs the same rendering checks.
  for (const path of [...paths, "/scan"]) {
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
      await expect
        .poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0), { timeout: 30000 })
        .toBe(true);
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

test("conference contact actions and QR display work without JavaScript", async ({ browser }, testInfo) => {
  const context = await browser.newContext({ ...testInfo.project.use, javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    await page.goto("/connect");
    await expect(page.getByRole("heading", { name: "Médéric Hurier (Fmind)", exact: true })).toBeVisible();
    await expect(page.getByText("Médéric Hurier (Fmind)", { exact: true })).toBeVisible();
    const linkedIn = page.getByRole("link", { name: "Connect on LinkedIn" });
    await expect(linkedIn).toBeInViewport();
    await expect(linkedIn).toHaveAttribute("href", "https://www.linkedin.com/in/fmind-dev/");
    const save = page.getByRole("link", { name: "Save my contact" });
    await expect(save).toBeInViewport();
    const cardDownload = page.waitForEvent("download");
    await save.click();
    const card = await cardDownload;
    expect(card.suggestedFilename()).toBe("mederic-hurier.vcf");
    expect(await card.failure()).toBeNull();
    await expect(page.getByRole("navigation", { name: "Connect with Médéric" }).getByRole("link"))
      .toHaveText(["Connect on LinkedIn", "Go to my website", "💾Save my contact"]);
    const website = page.getByRole("link", { name: "Go to my website", exact: true });
    await expect(website).toHaveAttribute("href", "/");
    await expect(website).toBeInViewport();
    await expect(page.getByRole("link", { name: "Email me" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Explore my work" })).toHaveCount(0);
    const home = page.locator("header").getByRole("link", { name: "Fmind.dev", exact: true });
    await expect(home).toHaveAttribute("href", "/");
    await home.focus();
    await expect(home).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(linkedIn).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(website).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(save).toBeFocused();
    await expect(page.getByRole("img", { name: /QR code/ })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("connect.png"), fullPage: true });
    await website.click();
    await expect(page).toHaveURL(/\/$/);
    await page.goto("/scan");
    await expect(page.getByRole("heading", { name: "Médéric Hurier (Fmind)", exact: true })).toBeVisible();
    const qr = page.getByRole("img", { name: /QR code opening Médéric Hurier/ });
    await expect(qr).toBeVisible();
    await expect(qr).toHaveJSProperty("naturalWidth", 296);
    await expect(qr).toBeInViewport();
    await page.screenshot({ path: testInfo.outputPath("scan.png"), fullPage: true });
    const destination = page.getByRole("link", { name: "www.fmind.dev/connect", exact: true });
    await expect(destination).toHaveAttribute("href", "https://www.fmind.dev/connect");
    await expect(page.getByText("Open your phone’s camera to connect on LinkedIn or save my contact.")).toHaveCount(0);
    await expect(page.getByText("Already on your phone? Tap the link above.")).toHaveCount(0);
    await page.setViewportSize({ width: 320, height: 568 });
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("scan-small-phone.png"), fullPage: true });
    for (const path of ["/connect", "/scan"]) {
      await page.setViewportSize({ width: 320, height: 740 });
      await page.goto(path);
      await page.evaluate(() => document.fonts.ready);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const brand = page.locator("header").getByRole("link", { name: "Fmind.dev", exact: true });
      await expect(brand).toHaveAttribute("href", "/");
      const logo = brand.locator("img");
      await expect(logo).toBeVisible();
      await expect(logo).toHaveAttribute("alt", "");
      expect(await logo.evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true);
      const logoBounds = await logo.boundingBox();
      const labelBounds = await brand.locator("span").boundingBox();
      expect(logoBounds.x + logoBounds.width).toBeLessThan(labelBounds.x);
      expect(Math.abs(logoBounds.y + logoBounds.height / 2 - labelBounds.y - labelBounds.height / 2))
        .toBeLessThanOrEqual(1);
      await expect(page.locator("h1")).toHaveCount(1);
      const portrait = page.getByRole("img", { name: "Médéric Hurier", exact: true });
      await expect(portrait).toBeVisible();
      const headingBounds = await page.locator("h1").boundingBox();
      const portraitBounds = await portrait.boundingBox();
      expect(portraitBounds.y + portraitBounds.height).toBeLessThanOrEqual(headingBounds.y);
      await expect(page.locator("h1")).toHaveCSS("color", "rgb(23, 78, 166)");
      await expect(page.getByText("AI Agents, MLOps & Security", { exact: true })).toBeVisible();
      await expect(page.locator("footer")).toHaveCount(0);
    }
  } finally {
    await context.close();
  }
});

test("menu remains usable when storage is blocked", async ({ page }) => {
  await page.addInitScript(() =>
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new DOMException("Storage blocked", "SecurityError");
      },
    })
  );
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.setViewportSize({ width: 1024, height: 844 });
  await page.locator("#section-menu summary").click();
  await expect(page.locator("#section-menu nav")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator("#section-menu nav")).toBeHidden();
  await expect(page.locator("#section-menu summary")).toBeFocused();
});

test("short desktop menu scrolls to every destination", async ({ page }) => {
  // A short desktop viewport exercises the dropdown scrolling boundary.
  await page.setViewportSize({ width: 1024, height: 320 });
  await page.goto("/");
  await page.locator("#section-menu summary").click();
  const menu = page.locator("#section-menu nav");
  const bounds = await menu.boundingBox();
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(320);
  const last = menu.getByRole("link").last();
  await last.focus();
  await expect(last).toBeInViewport();
  expect(await menu.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await page.keyboard.press("Escape");
  await expect(page.locator("#section-menu summary")).toBeFocused();
});

test("Theme and CLI appear only in the footer", async ({ page }) => {
  for (const width of [page.viewportSize().width, 640, 1280, 1536]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    const footer = page.getByRole("navigation", { name: "Footer navigation" });
    for (const [label, repository] of [["Theme", "theme"], ["CLI", "cli"]]) {
      const name = `${label} (external GitHub page)`;
      await expect(navigation.getByRole("link", { name, exact: true, includeHidden: true })).toHaveCount(0);
      const link = footer.getByRole("link", { name, exact: true });
      await expect(link).toHaveCount(1);
      await expect(link).toBeVisible();
      await expect(link).toHaveAttribute("href", `https://github.com/fmind/${repository}`);
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
      await expect(link).toHaveAttribute("target", "_blank");
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test("homepage presents the headline, six skills, and responsive social links", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.locator("header").getByRole("img", { name: "Fmind.dev logo", exact: true })).toBeVisible();
  await expect(page.locator("header a[href='/'] span")).toHaveText("Fmind.dev");
  await expect(page.locator("header a[href='/'] span")).toBeVisible({ visible: page.viewportSize().width >= 1280 });
  const sections = await page.locator("main section").evaluateAll((items) => items.map((item) => item.id));
  expect(sections).toEqual(["about", "services", "work-experience", "certifications", "projects"]);
  const white = "rgb(255, 255, 255)";
  const gray = await page.locator("main .hero").evaluate((element) => getComputedStyle(element).backgroundColor);
  expect(gray).not.toBe(white);
  const backgrounds = await page.locator("main section").evaluateAll((items) =>
    items.map((item) => getComputedStyle(item).backgroundColor)
  );
  expect(backgrounds).toEqual([white, gray, white, gray, white]);
  await expect(page.locator("#services .card").first()).toHaveCSS("background-color", white);
  await expect(page.locator("#work-experience .card-side").first()).toHaveCSS("background-color", gray);
  await expect(page.locator("#projects .card").first()).toHaveCSS("background-color", gray);
  const project = page.getByRole("link", { name: "Send Email", exact: true }).first();
  await expect(project).toHaveAttribute("href", "mailto:contact@fmind.dev");
  const mentoring = page.getByRole("link", { name: "Book Mentoring", exact: true }).first();
  await expect(page.getByText("Mentoring is a paid, one-hour session.", { exact: true })).toHaveCount(0);
  await expect(mentoring).not.toHaveAttribute("aria-describedby");
  await expect(mentoring).toHaveAttribute("href", /^https:\/\/calendar.google.com\//);
  await expect(page.locator("#services")).toContainText("Not available for new missions");
  const headline = page.locator("[data-hero-headline]");
  await expect(headline.locator(":scope > span")).toHaveText([
    "Freelance AI Architect • AI Agents, MLOps & Security",
    "PhD • VC Expert Advisor • AAIF Ambassador",
  ]);
  await expect(headline).toBeVisible();
  expect(await headline.evaluate((element) => parseFloat(getComputedStyle(element).fontSize)))
    .toBe(page.viewportSize().width >= 768 ? 24 : 18);
  if (page.viewportSize().width >= 1280) {
    const geometry = await headline.evaluate((element) => ({
      height: element.getBoundingClientRect().height,
      lineHeight: parseFloat(getComputedStyle(element).lineHeight),
    }));
    expect(geometry.height).toBeCloseTo(geometry.lineHeight * 2, 0);
  }
  await expect(page.locator("#about h4")).toHaveText([
    "Agentic Orchestration",
    "Production MLOps",
    "Security-First AI",
    "Technical Strategy",
    "Data Science & ML",
    "Python Development",
  ]);
  await expect(page.locator("#certifications").getByText("Active", { exact: true })).toHaveCount(2);
  await expect(page.locator("#certifications").getByText("Past credential", { exact: true })).toHaveCount(4);
  const socials = page.locator("header").getByRole("group", { name: "Social profiles" });
  await expect(page.locator("footer").getByRole("group", { name: "Social profiles" })).toHaveCount(0);
  const brand = await page.getByRole("link", { name: "Fmind.dev home", exact: true }).boundingBox();
  const socialBounds = await socials.boundingBox();
  expect(brand.x + brand.width).toBeLessThanOrEqual(socialBounds.x);
  expect(Math.abs(brand.y + brand.height / 2 - socialBounds.y - socialBounds.height / 2)).toBeLessThan(1);
  if (page.viewportSize().width < 1280) {
    const portfolio = await page.getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: "Portfolio", exact: true }).boundingBox();
    expect(Math.abs(portfolio.y + portfolio.height / 2 - socialBounds.y - socialBounds.height / 2)).toBeLessThan(1);
    expect(portfolio.x + portfolio.width).toBeLessThanOrEqual(socialBounds.x);
    await expect(page.locator("#section-menu summary")).toBeHidden();
  }
  const profiles = {
    "LinkedIn": "https://www.linkedin.com/in/fmind-dev/",
    "GitHub": "https://github.com/fmind",
    "X (Twitter)": "https://x.com/fmind_dev",
    "YouTube": "https://www.youtube.com/@fmind-dev",
    "Kaggle": "https://www.kaggle.com/freaxmind",
  };
  await expect(socials.getByRole("link")).toHaveCount(Object.keys(profiles).length);
  for (const [name, url] of Object.entries(profiles)) {
    const link = socials.getByRole("link", { name, exact: true });
    await expect(link).toBeInViewport();
    await expect(link).toHaveAttribute("href", url);
    const bounds = await link.locator("svg").boundingBox();
    expect(await link.evaluate((element) => getComputedStyle(element).color)).toBe(
      "rgb(32, 33, 36)",
    );
    const iconSize = page.viewportSize().width < 640 ? 16 : 20;
    expect(bounds.width).toBe(iconSize);
    expect(bounds.height).toBe(iconSize);
    const target = await link.boundingBox();
    expect(target.width).toBeGreaterThanOrEqual(page.viewportSize().width < 640 ? 24 : 44);
    expect(target.height).toBeGreaterThanOrEqual(40);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("home-header.png") });
  await page.locator("#about").scrollIntoViewIfNeeded();
  const biography = await page.locator("#about .prose").boundingBox();
  if (page.viewportSize().width >= 1280) expect(biography.width).toBeGreaterThan(1000);
  await page.screenshot({ path: testInfo.outputPath("home-about.png") });
  const footer = page.locator("footer");
  await expect(footer.locator("a[href^=\"https://\"]")).toHaveCount(2);
  // Resolve deferred section heights before inspecting the footer position.
  for (const section of await page.locator("main section").all()) await section.scrollIntoViewIfNeeded();
  await footer.scrollIntoViewIfNeeded();
  const rows = await footer.locator("p, nav").evaluateAll((elements) =>
    elements.map((element) => {
      const bounds = element.getBoundingClientRect();
      return bounds.y + bounds.height / 2;
    })
  );
  if (page.viewportSize().width >= 1280) {
    expect(Math.max(...rows) - Math.min(...rows)).toBeLessThan(1);
  }
  expect(await footer.evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThan(80);
  expect(await footer.locator("nav").evaluate((element) => parseFloat(getComputedStyle(element).fontSize)))
    .toBe(14);
  for (const link of await footer.locator("nav a").all()) {
    expect(await link.evaluate((element) => getComputedStyle(element).textDecorationLine)).toBe("underline");
    expect(await link.evaluate((element) => getComputedStyle(element).color)).toBe(
      "rgb(23, 78, 166)",
    );
  }
  await footer.getByRole("link", { name: "MCP", exact: true }).focus();
  await expect(footer.getByRole("link", { name: "MCP", exact: true })).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath("home-footer.png") });
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
      ["Google Sans Subset", "Google Sans Code Subset"].map(async (family) => {
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

test("keyboard skip link reaches main content", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
});

test("selected article filters expose their state and retain readable contrast", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/articles/");
  const filters = page.getByRole("navigation", { name: "Filter articles by tag" });
  const destinations = await filters.locator("a").evaluateAll((links) => links.map((link) => link.href));
  for (const destination of destinations) {
    await page.goto(destination);
    const current = filters.locator("[aria-current=\"page\"]");
    await expect(current).toHaveCount(1);
    await current.hover();
    const contrast = await current.evaluate((element) => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1;
      const context = canvas.getContext("2d");
      const surface = getComputedStyle(element.closest("section")).backgroundColor;
      const luminance = (color) => {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = surface;
        context.fillRect(0, 0, 1, 1);
        context.fillStyle = color;
        context.fillRect(0, 0, 1, 1);
        return [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map((channel) => {
          const value = channel / 255;
          return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        }).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
      };
      const style = getComputedStyle(element);
      const foreground = luminance(style.color);
      const background = luminance(style.backgroundColor);
      return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
    });
    expect(contrast, destination).toBeGreaterThanOrEqual(4.5);
  }
});

test("site stays light with a dark system preference and an old saved theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.addInitScript(() => localStorage.setItem("theme", "dark"));
  for (const path of ["/", "/connect", "/articles/", calculator]) {
    await page.goto(path);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page.locator("#theme-toggle")).toHaveCount(0);
    await expect(page.locator("meta[name=\"color-scheme\"]")).toHaveAttribute("content", "light");
    expect(await page.locator("html").evaluate((element) => getComputedStyle(element).colorScheme)).toBe("light");
  }
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
  await page.locator("#node").selectOption("g2-standard-12");
  await page.locator("#quant").selectOption("fp4");
  await page.locator("#billing").selectOption("cud-1y");
  await page.locator("#requests").fill("345");
  await page.locator("#update-comparison").click();
  await expect(page.locator("#requests")).toHaveValue("345");
  await expect(page.locator("#node")).toHaveValue("g2-standard-12");
  await expect(page.locator("#billing")).toHaveValue("cud-1y");
  await expect(page.locator("#billing-help")).toContainText("$460.09/node/month");
  expect(new URL(page.url()).searchParams.get("requests")).toBe("345");
  await page.goto("/articles/?q=agents");
  await expect(page.locator("main")).toContainText("agents");
  await context.close();
});

test("static hardware hints, commitments, and round chart workloads", async ({ page }, testInfo) => {
  await page.goto(calculator);
  await expect(page.locator("footer").getByRole("link", { name: "Sites", exact: true })).toHaveCount(0);
  const hint = page.locator("#hardware-guidance");
  await expect(hint).toContainText("G2");
  await expect(hint.locator("a, button, input, select")).toHaveCount(0);
  const initialHint = await hint.innerText();
  const initialNode = await page.locator("#node").inputValue();
  await page.locator("#model").selectOption("kimi-k3");
  await expect(hint).toContainText("2 nodes per replica · A3 Ultra");
  await expect(page.locator("#node")).toHaveValue(initialNode);
  await page.locator("#model").selectOption("qwen3-8-27b");
  await expect(hint).toHaveText(initialHint, { useInnerText: true });
  await page.locator("#node").selectOption("g4-standard-48");
  await page.locator("#billing").selectOption("cud-3y");
  await page.locator("#quant").selectOption("fp16");
  await page.locator("#duty").fill("25");
  await page.locator("#update-comparison").click();
  await expect(page.locator("#billing-help")).toContainText("$1,445.00/node/month, even while idle");
  await expect(hint).toHaveText(initialHint, { useInnerText: true });
  await page.reload();
  await expect(hint).toHaveText(initialHint, { useInnerText: true });
  await expect(page.locator("#billing")).toHaveValue("cud-3y");
  await page.locator("#cost-volume").focus();
  await page.locator("#cost-volume").press("ArrowRight");
  await expect(page.locator("[data-cost-output]")).toContainText("200 requests/day · 4,400 requests/month");
  await page.locator("#apply-demand").click();
  await expect(page.locator("#requests")).toHaveValue("200");
  await expect(hint).toHaveText(initialHint, { useInnerText: true });
  await page.locator("[data-cost-explorer]").screenshot({ path: `tmp/chart-${testInfo.project.name}.png` });
  await hint.screenshot({ path: `tmp/guidance-${testInfo.project.name}.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});

test("Fmind palette reaches page surfaces, controls, charts, and code", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(page.locator("body")).toHaveCSS("color", "rgb(32, 33, 36)");
  await expect(page.locator("h1")).toHaveCSS("color", "rgb(23, 78, 166)");
  await expect(page.locator("footer")).toHaveCSS("background-color", "rgb(241, 243, 244)");
  const button = page.getByRole("link", { name: "Book Mentoring", exact: true }).first();
  await expect(button).toHaveCSS("background-color", "rgb(23, 78, 166)");
  await expect(button).toHaveCSS("color", "rgb(255, 255, 255)");
  await button.focus();
  await expect(button).toBeFocused();
  await expect(button).toHaveCSS("outline-color", "rgb(23, 78, 166)");
  expect(await page.locator("h1").evaluate((element) => getComputedStyle(element, "::selection").backgroundColor))
    .toBe("rgb(210, 227, 252)");
  const manifest = await (await request.get("/static/site.webmanifest")).json();
  expect(manifest.theme_color).toBe("#174ea6");
  await expect(page.locator("meta[name=\"theme-color\"]")).toHaveAttribute("content", manifest.theme_color);

  await page.goto(calculator);
  for (
    const [selector, color] of [[".stroke-primary", "rgb(23, 78, 166)"], [".stroke-info", "rgb(0, 99, 109)"], [
      ".stroke-warning",
      "rgb(147, 73, 0)",
    ], [".stroke-secondary", "rgb(104, 29, 168)"]]
  ) {
    await expect(page.locator(selector).first()).toHaveCSS("stroke", color);
  }

  await expect(page.locator("input.input").first()).toHaveCSS("border-color", "rgb(89, 93, 98)");
  await expect(page.locator("select.select").first()).toHaveCSS("border-color", "rgb(89, 93, 98)");

  const profile = await (await request.get("/api/profile")).json();
  let foundCode = false;
  for (const article of profile.articles) {
    await page.goto(new URL(article.url).pathname);
    if (!(await page.locator(".chroma .k").count())) continue;
    foundCode = true;
    await expect(page.locator(".chroma").first()).toHaveCSS("background-color", "rgb(255, 255, 255)");
    await expect(page.locator(".chroma").first()).toHaveCSS("color", "rgb(32, 33, 36)");
    await expect(page.locator(".chroma .k").first()).toHaveCSS("color", "rgb(23, 78, 166)");
    await expect(page.locator(".chroma .k").first()).toHaveCSS("font-weight", "700");
    expect(
      await page.locator(".chroma .k").first().evaluate((element) =>
        getComputedStyle(element, "::selection").backgroundColor
      ),
    )
      .toBe("rgb(210, 227, 252)");
    break;
  }
  expect(foundCode).toBe(true);
});

test("footer stays compact with ordered discovery links", async ({ page }) => {
  await page.goto("/");
  const footer = page.locator("body > footer");
  const links = footer.getByRole("navigation", { name: "Footer navigation" }).getByRole("link");
  await expect(links).toHaveText([
    "MCP",
    "Scan",
    "Connect",
    "JSON Profile",
    "For AI Agents",
    "Privacy",
    "Theme",
    "CLI",
  ]);
  expect(await links.evaluateAll((items) => items.map((item) => item.getAttribute("href"))))
    .toEqual([
      "/mcp/server-card",
      "/scan",
      "/connect",
      "/api/profile",
      "/agents",
      "/privacy",
      "https://github.com/fmind/theme",
      "https://github.com/fmind/cli",
    ]);
  const scan = footer.getByRole("link", { name: "Scan", exact: true });
  await expect(scan).toHaveAttribute("href", "/scan");
  const padding = await footer.evaluate((element) => parseFloat(getComputedStyle(element).paddingTop));
  expect(padding).toBeLessThanOrEqual(24);
  await expect(links.first()).toHaveCSS("font-size", "14px");
  await expect(footer.locator("p").last()).toHaveCSS("font-size", "14px");
  const navigation = await footer.locator("nav").boundingBox();
  const bounds = await footer.boundingBox();
  expect(Math.abs(navigation.x + navigation.width / 2 - bounds.x - bounds.width / 2)).toBeLessThan(1);
});

test("narrow screens reflow and keep navigation reachable", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 740 });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const path of ["/", "/articles/", "/sites/", "/sites/llm-self-hosting/"]) {
    await page.goto(path);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    for (const name of ["Portfolio", "Articles", "Sites"]) {
      await expect(navigation.getByRole("link", { name, exact: true })).toBeInViewport();
    }
    const headerLinks = navigation.locator("a").filter({ visible: true });
    const boxes = await headerLinks.evaluateAll((links) =>
      links.map((link) => {
        const { x, y, width, height } = link.getBoundingClientRect();
        return { x, right: x + width, center: y + height / 2 };
      })
    );
    expect(boxes).toHaveLength(9);
    for (const box of boxes) {
      expect(box.x).toBeGreaterThanOrEqual(12);
      expect(box.right).toBeLessThanOrEqual(308);
      expect(box.center).toBe(boxes[0].center);
    }
    for (let index = 1; index < boxes.length; index++) {
      expect(boxes[index].x).toBeGreaterThanOrEqual(boxes[index - 1].right);
    }
    if (path === "/") {
      await expect(page.locator("#section-toolbar")).toBeHidden();
    } else {
      await expect(page.getByRole("navigation", { name: "Portfolio sections" })).toHaveCount(0);
    }
    // Visit deferred homepage sections as a reader would before reaching the footer.
    if (path === "/") {
      for (const section of await page.locator("main section").all()) await section.scrollIntoViewIfNeeded();
    }
    const footerNavigation = page.getByRole("navigation", { name: "Footer navigation" });
    await footerNavigation.scrollIntoViewIfNeeded();
    await expect(footerNavigation).toBeInViewport();
  }
  expect(errors).toEqual([]);
  await page.goto("/");
  await page.screenshot({ path: testInfo.outputPath("home-320.png") });
  for (
    const [width, wordmarkVisible] of [[390, false], [480, true], [540, true], [640, false], [820, true], [840, true], [
      1024,
      true,
    ]]
  ) {
    await page.setViewportSize({ width, height: 740 });
    const primary = page.getByRole("navigation", { name: "Primary navigation" });
    const brand = page.getByRole("link", { name: "Fmind.dev home", exact: true });
    await expect(brand.locator("span")).toBeVisible({ visible: wordmarkVisible });
    const brandBounds = await brand.boundingBox();
    const first = await primary.getByRole("link", { name: "Portfolio", exact: true }).boundingBox();
    const last = await primary.getByRole("link", { name: "Sites", exact: true }).boundingBox();
    const socials = await primary.getByRole("group", { name: "Social profiles" }).boundingBox();
    const linksWidth = last.x + last.width - first.x;
    expect(first.x).toBeGreaterThan(brandBounds.x + brandBounds.width);
    expect(last.x + last.width).toBeLessThan(socials.x);
    if (width === 480 || width === 540 || width >= 840) {
      expect(first.x + linksWidth / 2).toBeCloseTo(width / 2, 0);
    } else {
      // When the social group prevents exact centering, use the nearest free position.
      expect(socials.x - last.x - last.width).toBeLessThanOrEqual(8);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
  }
});

test("section toolbar stays below the header and clears content", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [1024, 1280, 1440, 1599]) {
    await page.setViewportSize({ width, height: 740 });
    await page.goto("/");
    const toolbar = page.locator("#section-toolbar");
    const summary = page.locator("#section-menu summary");
    const header = await page.locator("header").boundingBox();
    const bounds = await toolbar.boundingBox();
    expect(bounds.y).toBe(header.y + header.height);
    expect((await page.locator("main").boundingBox()).y).toBeGreaterThanOrEqual(bounds.y + bounds.height);
    await expect(page.locator("header #section-menu")).toHaveCount(0);
    expect((await summary.boundingBox()).height).toBeGreaterThanOrEqual(44);
    await summary.focus();
    await page.keyboard.press("Enter");
    await page.locator("#section-menu").getByRole("link", { name: "Services", exact: true }).click();
    await expect(page.locator("#services")).toBeFocused();
    await expect.poll(async () => (await page.locator("#services").boundingBox()).y)
      .toBeGreaterThanOrEqual(bounds.y + bounds.height);
    expect((await toolbar.boundingBox()).y).toBe(bounds.y);
    await summary.click();
    await page.locator("#services h2").click();
    await expect(page.locator("#section-menu")).not.toHaveAttribute("open");
  }
  await page.locator("#section-menu summary").click();
  await page.setViewportSize({ width: 1600, height: 900 });
  await expect(page.locator("#section-toolbar")).toBeHidden();
  await expect(page.locator("#section-menu")).not.toHaveAttribute("open");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#section-toolbar")).toBeHidden();
  await expect(page.locator("#section-menu nav")).toBeHidden();
});

test("section links, privacy, and browser-only presentation", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("link[rel=\"manifest\"]")).toHaveCount(0);
  await expect(page.locator("#services").getByRole("link", { name: "Send Email", exact: true })).toHaveAttribute(
    "href",
    "mailto:contact@fmind.dev",
  );
  await expect(page.locator("#services").getByRole("link", { name: "Book Mentoring", exact: true })).toHaveAttribute(
    "href",
    /^https:\/\/calendar.google.com\//,
  );
  const credentials = page.locator("[data-hero-headline] > span").nth(1);
  await expect(credentials.locator("span").first()).toHaveText("PhD • VC Expert Advisor");
  await page.locator("footer").getByRole("link", { name: "Privacy", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Privacy", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Operational logs", exact: true })).toHaveCount(0);
  await expect(page.locator("script:not([type=\"application/ld+json\"])")).toHaveCount(0);
  await page.goto("/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/");
  const anchor = page.locator(".heading-anchor").first();
  const fragment = await anchor.getAttribute("href");
  await anchor.click();
  await expect(page).toHaveURL(new RegExp(fragment + "$"));
  await page.reload();
  await expect(page.locator(fragment)).toBeInViewport();
});

test("section navigation follows clicks, scrolling, and direct links", async ({ page }, testInfo) => {
  if (page.viewportSize().width < 1024) await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto("/");
  const mobile = page.viewportSize().width < 1600;
  const navigation = page.getByRole("navigation", { name: "Portfolio sections" });
  if (!mobile) {
    const hero = page.locator("main .hero");
    const initial = await hero.boundingBox();
    expect(initial.x).toBe(0);
    expect(initial.width).toBe(page.viewportSize().width);
    await expect(navigation).toHaveCSS("width", "192px");
    await expect(navigation.getByRole("link", { name: "About", exact: true }).locator("span").last()).toHaveCSS(
      "opacity",
      "1",
    );
    await navigation.getByRole("link", { name: "About", exact: true }).focus();
    expect(await hero.boundingBox()).toEqual(initial);
    await page.getByRole("link", { name: "Fmind.dev home", exact: true }).focus();
    await expect(navigation).toHaveCSS("width", "192px");
  }
  if (mobile) await page.locator("#section-menu summary").click();
  await navigation.getByRole("link", { name: "Services", exact: true }).click();
  await expect(page).toHaveURL(/#services$/);
  if (mobile) {
    await expect(page.locator("#section-menu")).not.toHaveAttribute("open");
    await expect(page.locator("#services")).toBeFocused();
  }
  const links = page.locator("[data-section-link][href=\"/#services\"]");
  await expect(links.first()).toHaveAttribute("aria-current", "location");
  const header = await page.locator("header").boundingBox();
  const services = await page.locator("#services").boundingBox();
  expect(services.y).toBeGreaterThanOrEqual(header.y + header.height);
  if (!mobile) {
    const bounds = await navigation.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.width).toBeLessThanOrEqual(192);
    expect(services.x).toBe(0);
    expect(services.width).toBe(page.viewportSize().width);
    await expect(navigation).toBeInViewport();
  }
  await page.locator("#work-experience").evaluate((section) => section.scrollIntoView());
  await expect(page.locator("[data-section-link][href=\"/#work-experience\"]").first()).toHaveAttribute(
    "aria-current",
    "location",
  );
  await page.screenshot({ path: testInfo.outputPath("section-navigation.png") });
  await page.goto("/#projects");
  await expect.poll(async () => {
    const target = await page.locator("#projects").boundingBox();
    const top = await page.locator("header").boundingBox();
    const toolbar = await page.locator("#section-toolbar").boundingBox();
    return target.y - Math.max(top.y + top.height, toolbar ? toolbar.y + toolbar.height : 0);
  }).toBeGreaterThanOrEqual(0);
  await expect.poll(async () => {
    const target = await page.locator("#projects").boundingBox();
    const top = await page.locator("header").boundingBox();
    const toolbar = await page.locator("#section-toolbar").boundingBox();
    return target.y - Math.max(top.y + top.height, toolbar ? toolbar.y + toolbar.height : 0);
  }).toBeLessThanOrEqual(24);
  await expect(page.locator("[data-section-link][href=\"/#projects\"]").first()).toHaveAttribute(
    "aria-current",
    "location",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(page.locator("[data-section-link][aria-current]")).toHaveCount(0);
  const primary = page.getByRole("navigation", { name: "Primary navigation" });
  await primary.getByRole("link", { name: "Articles", exact: true }).click();
  await expect(primary.getByRole("link", { name: "Articles", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.locator("[data-section-link]")).toHaveCount(0);
  await primary.getByRole("link", { name: "Sites", exact: true }).click();
  await expect(primary.getByRole("link", { name: "Sites", exact: true })).toHaveAttribute("aria-current", "page");
});

test("section navigation never covers portfolio text", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [1024, 1280, 1440, 1600, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/#about");
    const rail = page.locator("aside");
    if (width < 1600) {
      await expect(rail).toBeHidden();
      await expect(page.locator("#section-menu summary")).toBeVisible();
    } else {
      await expect(rail).toBeVisible();
      const railBounds = await rail.boundingBox();
      for (const section of ["#about", "#work-experience", "#certifications", "#projects"]) {
        for (const element of await page.locator(`${section} p, ${section} h3, ${section} h4`).all()) {
          // Measure actual text, not a full-width box with centered content.
          const textRects = await element.evaluate((element) => {
            const range = document.createRange();
            range.selectNodeContents(element);
            return [...range.getClientRects()].filter((rect) => rect.width > 0).map((rect) => rect.x);
          });
          for (const x of textRects) {
            expect(x, `${width}px ${section}`).toBeGreaterThan(railBounds.x + railBounds.width);
          }
        }
      }
    }
  }
});

test("homepage availability is visible beside the primary actions", async ({ page }) => {
  await page.goto("/");
  const availability = page.locator("[data-availability]");
  await expect(availability).toContainText("Not available for new missions");
  await expect(availability).toContainText("Paid session");
  const lines = availability.locator("span");
  await expect(lines).toHaveCount(2);
  const consulting = await lines.first().boundingBox();
  const mentoring = await lines.last().boundingBox();
  expect(mentoring.y).toBeGreaterThanOrEqual(consulting.y + consulting.height);
  const actions = page.locator(".hero").getByRole("link", { name: "Book Mentoring", exact: true });
  await actions.scrollIntoViewIfNeeded();
  await expect(availability).toBeInViewport();
});

test("agent guide connects visitors to the calculator and verified skill", async ({ page, request }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "For AI Agents", exact: true }).click();
  await expect(page).toHaveURL(/\/agents$/);
  await expect(page.getByRole("heading", { name: "For AI agents", exact: true })).toBeVisible();
  const index = await (await request.get("/.well-known/agent-skills/index.json")).json();
  const skill = await request.get(new URL(index.skills[0].url).pathname);
  expect(skill.status()).toBe(200);
  const { createHash } = require("node:crypto");
  expect(index.skills[0].digest).toBe("sha256:" + createHash("sha256").update(await skill.body()).digest("hex"));
  await page.getByRole("link", { name: "calculator's shareable URLs" }).click();
  await expect(page).toHaveURL(/\/sites\/llm-self-hosting\/$/);
});

test("mobile reading keeps all section navigation out of the content", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [320, 390, 480, 768, 1023]) {
    await page.setViewportSize({ width, height: 740 });
    await page.goto("/");
    await expect(page.locator("#section-toolbar")).toBeHidden();
    await expect(page.locator("aside")).toBeHidden();
    const header = await page.locator("body > header").boundingBox();
    expect((await page.locator("main").boundingBox()).y).toBe(header.y + header.height);
    await page.getByRole("link", { name: "Scroll to About section" }).click();
    await expect(page).toHaveURL(/#about$/);
    await expect.poll(async () => (await page.locator("#about").boundingBox()).y)
      .toBeGreaterThanOrEqual(header.y + header.height);
    await expect(page.locator("#section-toolbar")).toBeHidden();
  }
});

test("article heading links copy the full section URL", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/");
  const link = page.locator(".heading-anchor").first();
  await expect(link).toHaveText("🔗");
  await expect(link).toHaveAccessibleName(/^Copy link to section:/);
  const destination = await link.evaluate((element) => element.href);
  await link.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Link copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(destination);
  await expect(page).toHaveURL(destination);
});

test("article anchors remain useful when clipboard access is denied", async ({ page }) => {
  await page.addInitScript(() =>
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: () => Promise.reject(new DOMException("Denied", "NotAllowedError")) },
    })
  );
  await page.goto("/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/");
  const link = page.locator(".heading-anchor").first();
  const destination = await link.evaluate((element) => element.href);
  await link.click();
  await expect(page).toHaveURL(destination);
  await expect(page.getByRole("status")).toContainText("Could not copy.");
});

test("article permalinks work without JavaScript", async ({ browser }, testInfo) => {
  const context = await browser.newContext({ ...testInfo.project.use, javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    await page.goto("/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/");
    const link = page.locator(".heading-anchor").first();
    await expect(link).toHaveAccessibleName(/^Link to section:/);
    const destination = await link.evaluate((element) => element.href);
    await link.click();
    await expect(page).toHaveURL(destination);
    await expect(page.locator(await link.getAttribute("href"))).toBeInViewport();
  } finally {
    await context.close();
  }
});
