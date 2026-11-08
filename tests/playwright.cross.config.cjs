const { defineConfig } = require("playwright/test");
const shared = require("./playwright.config.cjs");

module.exports = defineConfig({
  ...shared,
  fullyParallel: false,
  workers: 2,
  // Firefox stalls when seeded localStorage meets a context without JavaScript, and these
  // journeys never click behind the production consent banner, so start without a choice.
  use: { ...shared.use, storageState: undefined },
  testMatch: "cross-browser.spec.cjs",
  // On a CI runner, opening a WebKit page alone has taken 18s of the default 30s budget;
  // remote runs get room for browser startup, while the local server keeps the default.
  timeout: process.env.BROWSER_BASE_URL ? 60000 : 30000,
  outputDir: "../tmp/cross-browser-results",
  projects: ["firefox", "webkit"].flatMap((browserName) =>
    [{ width: 1440, height: 900 }, { width: 390, height: 844 }].map((viewport) => ({
      name: `${browserName}-${viewport.width}`,
      use: { browserName, viewport, colorScheme: "light", reducedMotion: "reduce" },
    }))
  ),
});
