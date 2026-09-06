const { defineConfig } = require("playwright/test");

const baseURL = process.env.BROWSER_BASE_URL || "http://127.0.0.1:8096";

module.exports = defineConfig({
  testDir: ".",
  testMatch: "browser.spec.cjs",
  outputDir: "../tmp/browser-results",
  workers: 1,
  reporter: "list",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [
    { name: "desktop-light", use: { viewport: { width: 1440, height: 900 }, colorScheme: "light" } },
    { name: "mobile-dark", use: { viewport: { width: 390, height: 844 }, colorScheme: "dark", isMobile: true } },
  ],
  webServer: process.env.BROWSER_BASE_URL ? undefined : {
    command: "uv run --locked www",
    cwd: process.cwd(),
    // Playwright merges this into the child environment; empty values disable
    // inherited collectors without changing the parent test process.
    env: {
      PORT: "8096",
      ENVIRONMENT: "production",
      OTEL_EXPORTER_OTLP_ENDPOINT: "",
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: "",
    },
    url: baseURL + "/health",
    stdout: "ignore",
    stderr: "ignore",
    timeout: 120000,
  },
});
