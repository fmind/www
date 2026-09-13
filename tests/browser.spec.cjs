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
    "/connect",
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
    await expect(page.getByRole("heading", { name: "Médéric Hurier (Fmind)" })).toBeVisible();
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
    await expect(page.getByRole("link", { name: "Email me" })).toHaveAttribute("href", "mailto:contact@fmind.dev");
    await expect(page.getByRole("link", { name: "Explore my work" })).toHaveAttribute("href", "/");
    const qr = page.getByRole("img", { name: "QR code for https://www.fmind.dev/connect", exact: true });
    await expect(qr).toBeVisible();
    await expect(qr).toHaveJSProperty("naturalWidth", 296);
    await page.screenshot({ path: testInfo.outputPath("connect.png"), fullPage: true });
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
  await page.locator("#menu-toggle").click();
  await expect(page.locator("#mobile-menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator("#mobile-menu")).toBeHidden();
  await expect(page.locator("#menu-toggle")).toBeFocused();
});

test("Theme and CLI follow Articles and Sites as external menu links", async ({ page }) => {
  for (const width of [page.viewportSize().width, 640, 1280, 1536]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/articles/");
    const navigation = page.getByRole("navigation", { name: "Primary navigation" });
    const menuButton = page.getByRole("button", { name: "Menu", exact: true });
    if (await menuButton.isVisible()) await menuButton.click();
    for (const [label, repository] of [["Theme", "theme"], ["CLI", "cli"]]) {
      const links = navigation.getByRole("link", { name: `${label} (external GitHub page)`, exact: true });
      for (const link of await links.all()) {
        await expect(link).toHaveAttribute("href", `https://github.com/fmind/${repository}`);
        await expect(link).toHaveAttribute("rel", "noopener noreferrer");
        await expect(link).toHaveAttribute("target", "_blank");
      }
      await expect(links.filter({ visible: true }).first()).toBeVisible();
    }
    const menu = await menuButton.isVisible() ? page.locator("#mobile-menu") : navigation;
    const destinations = await menu.locator(
      "a[href=\"/articles/\"], a[href=\"/sites/\"], a[href=\"https://github.com/fmind/theme\"], a[href=\"https://github.com/fmind/cli\"]",
    )
      .filter({ visible: true }).evaluateAll((links) => links.map((link) => link.getAttribute("href")));
    expect(destinations).toEqual([
      "/articles/",
      "/sites/",
      "https://github.com/fmind/theme",
      "https://github.com/fmind/cli",
    ]);
    await page.goto("/");
    await expect(page.locator("main #theme, main #cli")).toHaveCount(0);
    await expect(page.locator("main section").last()).toHaveAttribute("id", "services");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test("homepage presents the headline, six skills, and accessible social header", async ({ page }, testInfo) => {
  await page.goto("/");
  const headline = page.locator("[data-hero-headline]");
  await expect(headline.locator(":scope > span")).toHaveText([
    "AI Security Architect (PhD) • VC Expert Advisor • AAIF Ambassador",
    "GCP Certified Cloud Architect • AI, Agents & Security",
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
  const socials = page.getByRole("group", { name: "Social profiles" });
  const profiles = {
    "LinkedIn": "https://www.linkedin.com/in/fmind-dev/",
    "X (Twitter)": "https://x.com/fmind_dev",
    "Bluesky": "https://bsky.app/profile/fmind-dev.bsky.social",
    "Medium": "https://fmind.medium.com/",
    "GitHub": "https://github.com/fmind",
    "YouTube": "https://www.youtube.com/@fmind-dev",
    "Hugging Face": "https://huggingface.co/fmind",
    "Kaggle": "https://www.kaggle.com/freaxmind",
    "Credly": "https://www.credly.com/users/fmind",
  };
  await expect(socials.getByRole("link")).toHaveCount(Object.keys(profiles).length);
  for (const [name, url] of Object.entries(profiles)) {
    const link = socials.getByRole("link", { name, exact: true });
    await expect(link).toBeInViewport();
    await expect(link).toHaveAttribute("href", url);
    const bounds = await link.locator("svg").boundingBox();
    expect(await link.evaluate((element) => getComputedStyle(element).color)).toBe(
      await page.locator("header .text-primary").first().evaluate((element) => getComputedStyle(element).color),
    );
    expect(bounds.width).toBe(20);
    expect(bounds.height).toBe(20);
    const target = await link.boundingBox();
    expect(target.width).toBeGreaterThanOrEqual(40);
    expect(target.height).toBeGreaterThanOrEqual(40);
  }
  await page.screenshot({ path: testInfo.outputPath("home-header.png") });
  await page.locator("#about").scrollIntoViewIfNeeded();
  const biography = await page.locator("#about .prose").boundingBox();
  if (page.viewportSize().width >= 1280) expect(biography.width).toBeGreaterThan(1000);
  await page.screenshot({ path: testInfo.outputPath("home-about.png") });
  const footer = page.locator("footer");
  await expect(footer.locator("a[href^=\"https://\"]")).toHaveCount(0);
  await footer.scrollIntoViewIfNeeded();
  const rows = await footer.locator("p, nav").evaluateAll((elements) =>
    elements.map((element) => element.getBoundingClientRect().y)
  );
  if (page.viewportSize().width >= 1280) {
    expect(Math.max(...rows) - Math.min(...rows)).toBeLessThan(8);
  }
  expect(await footer.evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThan(80);
  expect(await footer.locator("nav").evaluate((element) => parseFloat(getComputedStyle(element).fontSize)))
    .toBeGreaterThanOrEqual(14);
  for (const link of await footer.locator("nav a").all()) {
    expect(await link.evaluate((element) => getComputedStyle(element).textDecorationLine)).toBe("underline");
    expect(await link.evaluate((element) => getComputedStyle(element).color)).toBe(
      await page.locator("header .text-primary").first().evaluate((element) => getComputedStyle(element).color),
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
  const button = page.getByRole("link", { name: "Book a Session", exact: true });
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

test("narrow screens reflow and keep navigation reachable", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 740 });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const path of ["/", "/articles/", "/sites/", "/sites/llm-self-hosting/"]) {
    await page.goto(path);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const menu = page.getByRole("button", { name: "Menu", exact: true });
    await menu.click();
    await expect(page.locator("#mobile-menu")).toBeInViewport();
    await page.keyboard.press("Escape");
    await expect(menu).toBeFocused();
    for (const link of await page.getByRole("group", { name: "Social profiles" }).getByRole("link").all()) {
      await expect(link).toBeInViewport();
    }
    await page.locator("footer").scrollIntoViewIfNeeded();
    await expect(page.getByRole("navigation", { name: "Footer navigation" })).toBeInViewport();
  }
  expect(errors).toEqual([]);
  await page.goto("/");
  await page.screenshot({ path: testInfo.outputPath("home-320.png") });
});
