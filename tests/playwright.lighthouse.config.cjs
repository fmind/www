const { defineConfig } = require("playwright/test");
const shared = require("./playwright.config.cjs");

const baseURL = process.env.BROWSER_BASE_URL || "http://127.0.0.1:8098";

module.exports = defineConfig({
  ...shared,
  use: { ...shared.use, baseURL },
  webServer: shared.webServer && {
    ...shared.webServer,
    env: { ...shared.webServer.env, PORT: "8098" },
    url: baseURL + "/health",
  },
  testMatch: "lighthouse.spec.cjs",
  outputDir: "../tmp/lighthouse-runner",
  projects: [{ name: "portfolio-lighthouse" }],
});
