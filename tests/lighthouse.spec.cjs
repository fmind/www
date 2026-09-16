const { test } = require("playwright/test");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");

// Reuse Playwright's bounded webServer lifecycle; no second server launcher.
test("all portfolio pages meet the strict Lighthouse contract", async ({ baseURL }) => {
  test.setTimeout(25 * 60 * 1000);
  const { stdout } = await promisify(execFile)(
    process.execPath,
    ["scripts/lighthouse.mjs", "--base-url", baseURL, "--mode", "portfolio"],
    { timeout: 24 * 60 * 1000, maxBuffer: 1024 * 1024 },
  );
  process.stdout.write(stdout);
});
