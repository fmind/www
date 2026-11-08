import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { access, chmod, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import * as harness from "./lighthouse.mjs";

const REPOSITORY_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPOSITORY_TMP = join(REPOSITORY_ROOT, "tmp");
const BASE_URL = new URL("https://candidate.example/");
const MAX_SITEMAP_BYTES = 2 * 1024 * 1024;
const CATEGORIES = ["performance", "accessibility", "best-practices", "seo", "agentic-browsing"];

function sitemapResponse(
  chunks,
  {
    cancel,
    close = true,
    contentType = "application/xml; charset=utf-8",
    url = "https://candidate.example/sitemap.xml",
  } = {},
) {
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(Buffer.from(chunk));
      if (close) controller.close();
    },
    cancel,
  });
  return {
    body,
    headers: new Headers({ "content-type": contentType }),
    ok: true,
    status: 200,
    url,
  };
}

function perfectReport(audit) {
  return {
    categories: Object.fromEntries(CATEGORIES.map((category) => [category, { score: 1 }])),
    finalDisplayedUrl: audit.url,
    lighthouseVersion: harness.LIGHTHOUSE_VERSION,
    requestedUrl: audit.url,
  };
}

test("parseArguments accepts only the documented CLI contract", () => {
  assert.deepEqual(harness.parseArguments(["--base-url=https://candidate.example"]), {
    allowSandbox: false,
    baseUrl: "https://candidate.example",
    help: false,
  });
  assert.equal(harness.parseArguments(["--base-url", "http://127.0.0.1:8000"]).baseUrl, "http://127.0.0.1:8000");
  assert.equal(harness.parseArguments(["--allow-sandbox"]).allowSandbox, true);
  assert.equal(harness.parseArguments(["--help"]).help, true);

  assert.throws(() => harness.parseArguments([]), /base-url is required/u);
  assert.throws(
    () => harness.parseArguments(["--allow-sandbox", "--base-url=https://candidate.example"]),
    /cannot be combined/u,
  );
  assert.throws(() => harness.parseArguments(["--wat"]), /unknown argument/u);
  assert.throws(
    () => harness.parseArguments(["--base-url=https://candidate.example", "--mode=portfolio"]),
    /unknown argument: --mode/u,
  );
  assert.throws(
    () => harness.parseArguments(["--base-url", "https://candidate.example", "--base-url=https://other.example"]),
    /only be specified once/u,
  );
  assert.throws(() => harness.parseArguments(["--base-url", "--help"]), /--base-url requires a value/u);
});

test("normalizeBaseUrl accepts an origin and rejects URL authority or path expansion", () => {
  assert.equal(harness.normalizeBaseUrl("https://candidate.example").href, "https://candidate.example/");
  for (
    const invalid of [
      "ftp://candidate.example",
      "https://user@candidate.example",
      "https://candidate.example/path",
      "https://candidate.example/?query=1",
      "https://candidate.example/#fragment",
    ]
  ) {
    assert.throws(() => harness.normalizeBaseUrl(invalid));
  }
});

test(
  "runProcess kills the full process group after a timeout",
  { skip: process.platform === "win32" },
  async () => {
    const grandchildProgram = "process.on('SIGTERM', () => {}); setInterval(() => {}, 1000)";
    const parentProgram = `
      const { spawn } = require("node:child_process");
      const grandchild = spawn(process.execPath, ["-e", ${JSON.stringify(grandchildProgram)}], {
        stdio: "ignore",
      });
      process.stdout.write(String(grandchild.pid));
      setInterval(() => {}, 1000);
    `;

    const result = await harness.runProcess(process.execPath, ["-e", parentProgram], {
      killGraceMs: 100,
      timeoutMs: 500,
    });
    const grandchildPid = Number(result.stdout);

    assert.equal(result.timedOut, true);
    assert.ok(Number.isSafeInteger(grandchildPid) && grandchildPid > 0);
    let exited = false;
    for (let attempt = 0; attempt < 50; attempt += 1) {
      try {
        process.kill(grandchildPid, 0);
      } catch (error) {
        if (error?.code !== "ESRCH") throw error;
        exited = true;
        break;
      }
      // A killed grandchild can remain observable as a zombie until PID 1 reaps it.
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 20));
    }
    assert.equal(exited, true);
  },
);

test("prepareArtifactDirectories keeps artifacts below the repository tmp directory", async () => {
  await assert.rejects(harness.prepareArtifactDirectories("tmp/../reports"), /inside.*tmp/u);
  await assert.rejects(harness.prepareArtifactDirectories(join(tmpdir(), "reports")), /inside.*tmp/u);
});

test("prepareArtifactDirectories rejects a symlink before creating through it", async (context) => {
  // A fresh checkout has no generated directories yet.
  await mkdir(REPOSITORY_TMP, { recursive: true });
  const external = await mkdtemp(join(tmpdir(), "www-lighthouse-external-"));
  const fixture = await mkdtemp(join(REPOSITORY_TMP, "lighthouse-symlink-test-"));
  context.after(async () => {
    await rm(fixture, { force: true, recursive: true });
    await rm(external, { force: true, recursive: true });
  });

  const link = join(fixture, "escape");
  await symlink(external, link, "dir");
  await assert.rejects(
    harness.prepareArtifactDirectories(join(link, "artifacts")),
    /symbolic link|outside.*tmp/u,
  );
  await assert.rejects(access(join(external, "artifacts")), { code: "ENOENT" });
});

test("prepareArtifactDirectories clears reports left by an earlier run", async (context) => {
  await mkdir(REPOSITORY_TMP, { recursive: true });
  const fixture = await mkdtemp(join(REPOSITORY_TMP, "lighthouse-stale-test-"));
  context.after(async () => {
    await rm(fixture, { force: true, recursive: true });
  });
  await mkdir(join(fixture, "reports"));
  const stale = join(fixture, "reports", "003-connect-desktop.json");
  await writeFile(stale, "{}", "utf8");

  const { reportsDirectory } = await harness.prepareArtifactDirectories(fixture);

  await access(reportsDirectory);
  await assert.rejects(access(stale), { code: "ENOENT" });
});

test("the harness runs when Node starts it through a symbolic link", async (context) => {
  await mkdir(REPOSITORY_TMP, { recursive: true });
  const fixture = await mkdtemp(join(REPOSITORY_TMP, "lighthouse-entry-test-"));
  context.after(async () => {
    await rm(fixture, { force: true, recursive: true });
  });
  const link = join(fixture, "lighthouse.mjs");
  await symlink(join(REPOSITORY_ROOT, "scripts", "lighthouse.mjs"), link);

  // A silent exit 0 here would let a qualification pass without auditing a page.
  const { stdout } = await promisify(execFile)(process.execPath, [link, "--help"], { timeout: 30_000 });
  assert.match(stdout, /--base-url/u);
});

test("parseSitemapPaths validates canonical pages and retargets only their paths", () => {
  const xml = `<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.fmind.dev/articles/z/</loc></url>
  <url><loc>https://www.fmind.dev/</loc></url>
</urlset>`;
  assert.deepEqual(harness.parseSitemapPaths(xml, BASE_URL), {
    paths: ["/", "/articles/z/"],
    sitemapOrigin: "https://www.fmind.dev",
  });
});

test("parseSitemapPaths rejects malformed or unsafe sitemap locations", async (context) => {
  const cases = {
    "cross-origin location": ["https://www.fmind.dev/", "https://other.example/articles/"],
    "duplicate path": ["https://www.fmind.dev/", "https://www.fmind.dev/"],
    "fragment location": ["https://www.fmind.dev/#top"],
    "non-page path": ["https://www.fmind.dev/articles"],
    "query location": ["https://www.fmind.dev/?page=1"],
    "unsupported entity": ["https://www.fmind.dev/articles/&copy;/"],
    "whitespace within location": ["https://www.fmind.dev/art\nicles/"],
  };
  for (const [name, locations] of Object.entries(cases)) {
    await context.test(name, () => {
      const xml = `<urlset>${locations.map((location) => `<url><loc>${location}</loc></url>`).join("")}</urlset>`;
      assert.throws(() => harness.parseSitemapPaths(xml, BASE_URL));
    });
  }
  assert.throws(
    () => harness.parseSitemapPaths("<urlset><url><loc>https://www.fmind.dev/</loc></url>", BASE_URL),
    /urlset/u,
  );
  assert.throws(
    () =>
      harness.parseSitemapPaths(
        "<urlset></urlset><urlset><url><loc>https://www.fmind.dev/</loc></url></urlset>",
        BASE_URL,
      ),
    /urlset/u,
  );
  assert.throws(() => harness.parseSitemapPaths("<not-a-sitemap />", BASE_URL), /urlset/u);
});

test("fetchSitemap reads a fragmented response stream", async () => {
  const response = sitemapResponse([
    "<urlset><url><loc>https://www.fmind.dev/",
    "</loc></url></urlset>",
  ]);
  const result = await harness.fetchSitemap(BASE_URL, async () => response);
  assert.deepEqual(result, { paths: ["/"], sitemapOrigin: "https://www.fmind.dev" });
});

test("fetchSitemap cancels its decoded stream immediately above the 2 MiB cap", async () => {
  let cancelled = false;
  const response = sitemapResponse([Buffer.alloc(MAX_SITEMAP_BYTES + 1, "x")], {
    cancel() {
      cancelled = true;
    },
    close: false,
  });
  await assert.rejects(harness.fetchSitemap(BASE_URL, async () => response), /exceeds 2097152 bytes/u);
  assert.equal(cancelled, true);
});

test("fetchSitemap reports a cancellation failure without hiding the size violation", async () => {
  const response = sitemapResponse([Buffer.alloc(MAX_SITEMAP_BYTES + 1, "x")], {
    cancel() {
      throw new Error("cancel failed");
    },
    close: false,
  });
  await assert.rejects(
    harness.fetchSitemap(BASE_URL, async () => response),
    /sitemap exceeds 2097152 bytes.*cancel its stream: cancel failed/u,
  );
});

test("fetchSitemap rejects missing and failed response bodies", async () => {
  const metadata = {
    headers: new Headers({ "content-type": "application/xml" }),
    ok: true,
    status: 200,
    url: "https://candidate.example/sitemap.xml",
  };
  await assert.rejects(harness.fetchSitemap(BASE_URL, async () => ({ ...metadata, body: null })), /body/u);

  const body = new ReadableStream({
    start(controller) {
      controller.error(new Error("stream failed"));
    },
  });
  await assert.rejects(
    harness.fetchSitemap(BASE_URL, async () => ({ ...metadata, body })),
    /read sitemap body.*stream failed/u,
  );
});

test("fetchSitemap rejects an invalid XML media type", async () => {
  const response = sitemapResponse(["<urlset><url><loc>https://www.fmind.dev/</loc></url></urlset>"], {
    contentType: "text/notxml",
  });
  await assert.rejects(harness.fetchSitemap(BASE_URL, async () => response), /unexpected content type/u);
});

test("the portfolio plan audits every page and both calculators on desktop and mobile", () => {
  const paths = [
    "/",
    "/connect",
    "/privacy",
    "/articles/",
    "/news/",
    "/sites/",
    "/sites/llm-self-hosting/",
    "/sites/mcp-context-cost/",
    "/articles/new/",
    "/sites/tool/",
  ];
  const portfolio = harness.buildAuditPlan(BASE_URL);
  assert.equal(portfolio.length, 16);
  assert.deepEqual([...new Set(portfolio.map((audit) => audit.path))], paths.slice(0, 8));
  assert.deepEqual(new Set(portfolio.map((audit) => audit.formFactor)), new Set(["desktop", "mobile"]));
  assert.equal(new Set(portfolio.map((audit) => audit.artifact)).size, 16);
  assert.deepEqual(portfolio[0], {
    artifact: "reports/001-home-desktop.json",
    formFactor: "desktop",
    index: 1,
    path: "/",
    url: "https://candidate.example/",
  });
  assert.ok(portfolio.every((audit) => new URL(audit.url).origin === BASE_URL.origin));
  harness.validateSitemapScope(paths);
  assert.throws(
    () => harness.validateSitemapScope(paths.filter((path) => path !== "/sites/llm-self-hosting/")),
    /required path/u,
  );
});

test("inspectReport accepts only exact categories and the audited page URL", () => {
  const audit = { url: "https://candidate.example/articles/test/" };
  assert.deepEqual(harness.inspectReport(perfectReport(audit), audit, BASE_URL).errors, []);

  const missing = perfectReport(audit);
  delete missing.categories.seo;
  assert.match(harness.inspectReport(missing, audit, BASE_URL).errors.join("\n"), /missing: seo/u);

  const imperfect = perfectReport(audit);
  imperfect.categories.performance.score = 0.99;
  assert.match(harness.inspectReport(imperfect, audit, BASE_URL).errors.join("\n"), /performance score is 0\.99/u);

  const unexpected = perfectReport(audit);
  unexpected.categories.pwa = { score: 1 };
  assert.match(harness.inspectReport(unexpected, audit, BASE_URL).errors.join("\n"), /unexpected category: pwa/u);

  const wrongRequest = perfectReport(audit);
  wrongRequest.requestedUrl = "https://candidate.example/articles/other/";
  assert.match(harness.inspectReport(wrongRequest, audit, BASE_URL).errors.join("\n"), /requested URL does not match/u);

  const escapedFinal = perfectReport(audit);
  escapedFinal.finalDisplayedUrl = "https://other.example/articles/test/";
  assert.match(harness.inspectReport(escapedFinal, audit, BASE_URL).errors.join("\n"), /final URL escaped or changed/u);

  const changedFinal = perfectReport(audit);
  changedFinal.finalDisplayedUrl = `${audit.url}?unexpected=1`;
  assert.match(harness.inspectReport(changedFinal, audit, BASE_URL).errors.join("\n"), /final URL escaped or changed/u);
});

test("sitemap accepts the canonical slashless contact page", () => {
  const xml = "<urlset><url><loc>https://www.fmind.dev/connect</loc></url></urlset>";
  assert.deepEqual(harness.parseSitemapPaths(xml, BASE_URL).paths, ["/connect"]);
  assert.throws(
    () => harness.parseSitemapPaths(xml.replace("/connect", "/unexpected"), BASE_URL),
    /must end in a slash/u,
  );
});

test("sitemap accepts the canonical privacy and agent pages", () => {
  for (const path of ["/privacy", "/agents"]) {
    const xml = `<urlset><url><loc>https://www.fmind.dev${path}</loc></url></urlset>`;
    assert.deepEqual(harness.parseSitemapPaths(xml, BASE_URL).paths, [path]);
  }
});

test("runAudit retries once on NO_NAVSTART and does not retry other score failures", async (context) => {
  await mkdir(REPOSITORY_TMP, { recursive: true });
  const fixture = await mkdtemp(join(REPOSITORY_TMP, "lighthouse-retry-test-"));
  context.after(async () => {
    await rm(fixture, { force: true, recursive: true });
  });

  const artifactDirectories = await harness.prepareArtifactDirectories(fixture);
  const audit = {
    artifact: "reports/001-home-desktop.json",
    formFactor: "desktop",
    index: 1,
    path: "/",
    url: "https://candidate.example/",
  };
  const toolchain = { chromiumPath: "/usr/bin/chromium" };

  let navstartCalls = 0;
  const recovered = await harness.runAudit(
    audit,
    BASE_URL,
    artifactDirectories,
    toolchain,
    async (_command, arguments_) => {
      navstartCalls += 1;
      const outputArgument = arguments_.find((item) => item.startsWith("--output-path="));
      const outputPath = outputArgument.slice("--output-path=".length);
      if (navstartCalls === 1) {
        const failedReport = {
          ...perfectReport(audit),
          categories: {
            ...perfectReport(audit).categories,
            "agentic-browsing": { score: null },
            performance: { score: null },
          },
          runtimeError: { code: "NO_NAVSTART", message: "NO_NAVSTART" },
        };
        await writeFile(outputPath, JSON.stringify(failedReport), "utf8");
        return { code: 1, signal: null, stderr: "NO_NAVSTART", stdout: "", timedOut: false };
      }
      await writeFile(outputPath, JSON.stringify(perfectReport(audit)), "utf8");
      return { code: 0, signal: null, stderr: "", stdout: "", timedOut: false };
    },
  );
  assert.equal(navstartCalls, 2);
  assert.equal(recovered.passed, true);

  let scoreFailureCalls = 0;
  const unrecovered = await harness.runAudit(
    audit,
    BASE_URL,
    artifactDirectories,
    toolchain,
    async (_command, arguments_) => {
      scoreFailureCalls += 1;
      const outputArgument = arguments_.find((item) => item.startsWith("--output-path="));
      const outputPath = outputArgument.slice("--output-path=".length);
      const report = perfectReport(audit);
      report.categories.accessibility.score = 0.95;
      await writeFile(outputPath, JSON.stringify(report), "utf8");
      return { code: 0, signal: null, stderr: "", stdout: "", timedOut: false };
    },
  );
  assert.equal(scoreFailureCalls, 1);
  assert.equal(unrecovered.passed, false);
  assert.equal(unrecovered.performanceRuns, undefined);
});

test("runAudit keeps only the tail of a failed Lighthouse debug stream", async (context) => {
  await mkdir(REPOSITORY_TMP, { recursive: true });
  const fixture = await mkdtemp(join(REPOSITORY_TMP, "lighthouse-detail-test-"));
  context.after(async () => {
    await rm(fixture, { force: true, recursive: true });
  });
  const artifactDirectories = await harness.prepareArtifactDirectories(fixture);
  const audit = {
    artifact: "reports/001-home-mobile.json",
    formFactor: "mobile",
    index: 1,
    path: "/",
    url: "https://candidate.example/",
  };
  const debugStream = `${"LH:status Loading page\n".repeat(1000)}Error: PROTOCOL_TIMEOUT\n    at Driver.sendCommand`;

  const result = await harness.runAudit(
    audit,
    BASE_URL,
    artifactDirectories,
    { chromiumPath: "/usr/bin/chromium" },
    async () => ({ code: 1, signal: null, stderr: debugStream, stdout: "", timedOut: false }),
  );

  assert.equal(result.passed, false);
  const [executionError] = result.errors;
  assert.match(executionError, /^lighthouse exited with code 1: …/u);
  assert.match(executionError, /Error: PROTOCOL_TIMEOUT\n {4}at Driver\.sendCommand$/u);
  assert.ok(executionError.length < 2200, `failure detail is ${executionError.length} characters`);
  assert.equal(
    harness.describeFailure({ ...audit, errors: ["performance score 0.99", "agentic-browsing\nscore 0.5"] }),
    "1: mobile / — performance score 0.99; agentic-browsing score 0.5",
  );
});

const MEDIAN_AUDIT = {
  artifact: "reports/002-articles-mobile.json",
  formFactor: "mobile",
  index: 2,
  path: "/articles/",
  url: "https://candidate.example/articles/",
};

function reportWith(scores, extra = {}) {
  const report = perfectReport(MEDIAN_AUDIT);
  for (const [category, score] of Object.entries(scores)) report.categories[category].score = score;
  return { ...report, ...extra };
}

// Plays one scripted Lighthouse report per call and records where each was written.
function scriptedLighthouse(reports) {
  const outputs = [];
  async function lighthouse(_command, arguments_) {
    const report = reports[outputs.length];
    const outputPath = arguments_.find((item) => item.startsWith("--output-path=")).slice("--output-path=".length);
    outputs.push(outputPath);
    assert.ok(report, `unexpected Lighthouse run ${outputs.length}`);
    await writeFile(outputPath, JSON.stringify(report), "utf8");
    return report.runtimeError
      ? { code: 1, signal: null, stderr: report.runtimeError.code, stdout: "", timedOut: false }
      : { code: 0, signal: null, stderr: "", stdout: "", timedOut: false };
  }
  return { lighthouse, outputs };
}

async function medianFixture(context) {
  await mkdir(REPOSITORY_TMP, { recursive: true });
  const fixture = await mkdtemp(join(REPOSITORY_TMP, "lighthouse-median-test-"));
  context.after(async () => {
    await rm(fixture, { force: true, recursive: true });
  });
  return harness.prepareArtifactDirectories(fixture);
}

test("runAudit judges a performance-only miss by the median of three kept runs", async (context) => {
  const artifactDirectories = await medianFixture(context);
  const { lighthouse, outputs } = scriptedLighthouse([
    reportWith({ performance: 0.97 }),
    reportWith({}),
    reportWith({}),
  ]);

  const result = await harness.runAudit(
    MEDIAN_AUDIT,
    BASE_URL,
    artifactDirectories,
    { chromiumPath: "/usr/bin/chromium" },
    lighthouse,
  );

  assert.equal(outputs.length, 3);
  assert.equal(result.passed, true);
  assert.deepEqual(result.errors, []);
  assert.equal(result.scores.performance, 1);
  assert.equal(result.performanceMedian, 1);
  assert.equal(result.artifact, MEDIAN_AUDIT.artifact);
  assert.deepEqual(result.performanceRuns, [
    { artifact: "reports/002-articles-mobile.json", score: 0.97 },
    { artifact: "reports/002-articles-mobile-performance-run-2.json", score: 1 },
    { artifact: "reports/002-articles-mobile-performance-run-3.json", score: 1 },
  ]);
  for (const run of result.performanceRuns) await access(join(artifactDirectories.outputDirectory, run.artifact));

  const manifest = { audits: [MEDIAN_AUDIT], baseUrl: BASE_URL.href };
  const summary = harness.summarize(manifest, [result], "passed");
  assert.equal(summary.passedAudits, 1);
  assert.deepEqual(summary.performanceReruns.map((audit) => audit.performanceRuns), [result.performanceRuns]);
  assert.match(
    harness.renderSummary(summary),
    /## Performance medians[\s\S]*- 2: mobile \/articles\/ — performance runs 0\.97, 1, 1; median 1; passed\n/u,
  );
});

test("runAudit fails a performance miss whose median stays below 1", async (context) => {
  const artifactDirectories = await medianFixture(context);
  const { lighthouse, outputs } = scriptedLighthouse([
    reportWith({ performance: 0.97 }),
    reportWith({}),
    reportWith({ performance: 0.98 }),
  ]);

  const result = await harness.runAudit(
    MEDIAN_AUDIT,
    BASE_URL,
    artifactDirectories,
    { chromiumPath: "/usr/bin/chromium" },
    lighthouse,
  );

  assert.equal(outputs.length, 3);
  assert.equal(result.passed, false);
  assert.equal(result.performanceMedian, 0.98);
  assert.equal(result.scores.performance, 0.98);
  assert.deepEqual(result.errors, ["performance median is 0.98 over runs 0.97, 1, 0.98, expected 1"]);
  const summary = harness.summarize(
    { audits: [MEDIAN_AUDIT], baseUrl: BASE_URL.href },
    [result],
    "failed",
  );
  assert.deepEqual(summary.failures[0].performanceRuns, result.performanceRuns);
  assert.match(harness.renderSummary(summary), /performance runs 0\.97, 1, 0\.98; median 0\.98; failed/u);
});

test("runAudit re-runs performance only when every other category is exactly 1", async (context) => {
  const artifactDirectories = await medianFixture(context);
  const cases = {
    "another category also misses": reportWith({ performance: 0.9, seo: 0.92 }),
    "performance has no score": reportWith({ performance: null }),
    "the run reports a runtime error": reportWith(
      { performance: 0.9 },
      { runtimeError: { code: "PROTOCOL_TIMEOUT", message: "PROTOCOL_TIMEOUT" } },
    ),
  };
  for (const [name, report] of Object.entries(cases)) {
    await context.test(name, async () => {
      const { lighthouse, outputs } = scriptedLighthouse([report]);
      const result = await harness.runAudit(
        MEDIAN_AUDIT,
        BASE_URL,
        artifactDirectories,
        { chromiumPath: "/usr/bin/chromium" },
        lighthouse,
      );
      assert.equal(outputs.length, 1);
      assert.equal(result.passed, false);
      assert.equal(result.performanceRuns, undefined);
    });
  }
});

test("runAudit fails when a performance re-run misses another category", async (context) => {
  const artifactDirectories = await medianFixture(context);
  const { lighthouse, outputs } = scriptedLighthouse([
    reportWith({ performance: 0.97 }),
    reportWith({ accessibility: 0.98 }),
    reportWith({}),
  ]);

  const result = await harness.runAudit(
    MEDIAN_AUDIT,
    BASE_URL,
    artifactDirectories,
    { chromiumPath: "/usr/bin/chromium" },
    lighthouse,
  );

  assert.equal(outputs.length, 3);
  assert.equal(result.passed, false);
  assert.equal(result.performanceMedian, null);
  assert.equal(result.scores.performance, 0.97);
  assert.deepEqual(result.errors, [
    "performance runs 0.97, 1, 1 have no valid median",
    "performance run 2: accessibility score is 0.98, expected 1",
  ]);
});

test("runAudit keeps the NO_NAVSTART retry inside each performance run", async (context) => {
  const artifactDirectories = await medianFixture(context);
  const navstart = reportWith(
    { "agentic-browsing": null, performance: null },
    { runtimeError: { code: "NO_NAVSTART", message: "NO_NAVSTART" } },
  );
  const { lighthouse, outputs } = scriptedLighthouse([
    navstart,
    reportWith({ performance: 0.97 }),
    navstart,
    reportWith({}),
    reportWith({}),
  ]);

  const result = await harness.runAudit(
    MEDIAN_AUDIT,
    BASE_URL,
    artifactDirectories,
    { chromiumPath: "/usr/bin/chromium" },
    lighthouse,
  );

  assert.equal(outputs.length, 5);
  assert.equal(result.passed, true);
  assert.deepEqual(result.performanceRuns.map((run) => run.score), [0.97, 1, 1]);
});

test("allowChromiumSandbox installs an AppArmor userns profile only for a safe executable path", async (context) => {
  await mkdir(REPOSITORY_TMP, { recursive: true });
  const fixture = await mkdtemp(join(REPOSITORY_TMP, "lighthouse-sandbox-test-"));
  context.after(async () => {
    await rm(fixture, { force: true, recursive: true });
  });
  const fakeChromium = join(fixture, "chrome");
  await writeFile(fakeChromium, "#!/bin/sh\n");
  await chmod(fakeChromium, 0o755);

  const calls = [];
  let installedProfile = "";
  await harness.allowChromiumSandbox(fakeChromium, {
    outputDirectory: fixture,
    runProcessImplementation: async (command, args) => {
      calls.push([command, ...args]);
      if (args[0] === "install") installedProfile = await readFile(args[3], "utf8");
      return { code: 0, signal: null, stdout: "", stderr: "", timedOut: false };
    },
  });

  assert.equal(calls.length, 2);
  assert.equal(calls[0][0], "sudo");
  assert.equal(calls[0][1], "install");
  assert.equal(calls[0][5], "/etc/apparmor.d/www-lighthouse-chromium");
  assert.deepEqual(calls[1], ["sudo", "apparmor_parser", "-r", "/etc/apparmor.d/www-lighthouse-chromium"]);
  assert.match(
    installedProfile,
    new RegExp(`profile www-lighthouse-chromium "${fakeChromium}" flags=\\(unconfined\\)`),
  );
  await assert.rejects(access(join(fixture, "www-lighthouse-chromium.apparmor")), { code: "ENOENT" });

  await assert.rejects(harness.allowChromiumSandbox("/bad/\"quote/chrome"), /invalid Chromium executable path/u);
});
