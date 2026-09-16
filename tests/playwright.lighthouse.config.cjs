const { defineConfig } = require("playwright/test");
const shared = require("./playwright.config.cjs");

module.exports = defineConfig({
  ...shared,
  testMatch: "lighthouse.spec.cjs",
  outputDir: "../tmp/lighthouse-runner",
  projects: [{ name: "portfolio-lighthouse" }],
});
