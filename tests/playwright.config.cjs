const { defineConfig } = require("playwright/test");

const baseURL = process.env.BROWSER_BASE_URL || "http://127.0.0.1:8096";

module.exports = defineConfig({
  testDir: ".",
  testMatch: "browser.spec.cjs",
  outputDir: "../tmp/browser-results",
  // A committed test.only would silently narrow the CI gate; the other configs inherit this.
  forbidOnly: !!process.env.CI,
  // Each context is isolated and the shared server only serves immutable data.
  // Run Chromium journeys in parallel across workers; cross-browser overrides this
  // to two workers without intra-file parallelism because four on CI starve WebKit.
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  reporter: "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    // Production shows the consent banner over the footer. Journeys start with a recorded
    // rejection so they exercise the page and never load Google Analytics from CI.
    ...(process.env.BROWSER_BASE_URL && {
      storageState: {
        cookies: [],
        origins: [{ origin: new URL(baseURL).origin, localStorage: [{ name: "fmind-consent", value: "denied" }] }],
      },
    }),
  },
  projects: [
    { name: "desktop-light", use: { viewport: { width: 1440, height: 900 }, colorScheme: "light" } },
    { name: "mobile-light", use: { viewport: { width: 390, height: 844 }, colorScheme: "light", isMobile: true } },
  ],
  webServer: process.env.BROWSER_BASE_URL ? undefined : {
    command: "uv run --locked --no-dev www",
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
