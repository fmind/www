const { expect, test } = require("playwright/test");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");

// Reuse Playwright's bounded webServer lifecycle; no second server launcher.
test("all portfolio pages meet the strict Lighthouse contract", async ({ baseURL }) => {
  test.setTimeout(25 * 60 * 1000);
  let stdout;
  try {
    ({ stdout } = await promisify(execFile)(
      process.execPath,
      ["scripts/lighthouse.mjs", "--base-url", baseURL, "--mode", "portfolio"],
      { timeout: 24 * 60 * 1000, maxBuffer: 1024 * 1024 },
    ));
  } catch (error) {
    // The rejection message carries stderr; keep the per-audit progress too.
    process.stdout.write(error.stdout ?? "");
    throw error;
  }
  process.stdout.write(stdout);
  // Exit 0 alone is not evidence: require the harness to report every planned audit as passed.
  const [, passed, planned] = /Lighthouse qualification passed: (\d+)\/(\d+) audits passed\./u.exec(stdout) ?? [];
  expect(Number(planned)).toBeGreaterThan(0);
  expect(passed).toBe(planned);
});
