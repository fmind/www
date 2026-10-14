const { defineConfig } = require("playwright/test");
const shared = require("./playwright.config.cjs");

module.exports = defineConfig({
  ...shared,
  // Firefox stalls when seeded localStorage meets a context without JavaScript, and these
  // journeys never click behind the production consent banner, so start without a choice.
  use: { ...shared.use, storageState: undefined },
  testMatch: "cross-browser.spec.cjs",
  outputDir: "../tmp/cross-browser-results",
  projects: ["firefox", "webkit"].flatMap((browserName) =>
    [{ width: 1440, height: 900 }, { width: 390, height: 844 }].map((viewport) => ({
      name: `${browserName}-${viewport.width}`,
      use: { browserName, viewport, colorScheme: "light", reducedMotion: "reduce" },
    }))
  ),
});
