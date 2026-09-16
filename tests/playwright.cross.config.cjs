const { defineConfig } = require("playwright/test");
const shared = require("./playwright.config.cjs");

module.exports = defineConfig({
  ...shared,
  testMatch: "cross-browser.spec.cjs",
  outputDir: "../tmp/cross-browser-results",
  projects: ["firefox", "webkit"].flatMap((browserName) =>
    [{ width: 1440, height: 900 }, { width: 390, height: 844 }].map((viewport) => ({
      name: `${browserName}-${viewport.width}`,
      use: { browserName, viewport, colorScheme: "light", reducedMotion: "reduce" },
    }))
  ),
});
