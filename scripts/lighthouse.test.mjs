import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

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
    lighthouseVersion: "13.4.1",
    requestedUrl: audit.url,
  };
}

test("parseArguments accepts only the documented CLI contract", () => {
  assert.deepEqual(
    harness.parseArguments(
      [
        "--base-url=https://candidate.example",
        "--mode",
        "smoke",
        "--output-dir=tmp/custom-lighthouse",
        "--plan",
      ],
      {},
    ),
    {
      baseUrl: "https://candidate.example",
      help: false,
      mode: "smoke",
      outputDir: "tmp/custom-lighthouse",
      plan: true,
    },
  );
  assert.equal(
    harness.parseArguments([], { LIGHTHOUSE_BASE_URL: "http://127.0.0.1:8000" }).baseUrl,
    "http://127.0.0.1:8000",
  );
  assert.equal(harness.parseArguments(["--help"], {}).help, true);

  assert.throws(() => harness.parseArguments([], {}), /base-url.*required/u);
  assert.throws(() => harness.parseArguments(["--wat"], {}), /unknown argument/u);
  assert.throws(
    () => harness.parseArguments(["--base-url", "https://candidate.example", "--base-url=https://other.example"], {}),
    /only be specified once/u,
  );
  assert.throws(() => harness.parseArguments(["--base-url", "--plan"], {}), /--base-url requires a value/u);
  assert.throws(
    () => harness.parseArguments(["--base-url=https://candidate.example", "--mode=quick"], {}),
    /full or smoke/u,
  );
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

test("resolveOutputDirectory contains artifacts below the repository tmp directory", () => {
  assert.equal(harness.resolveOutputDirectory("tmp/lighthouse"), join(REPOSITORY_TMP, "lighthouse"));
  assert.throws(() => harness.resolveOutputDirectory("tmp/../reports"), /inside.*tmp/u);
  assert.throws(() => harness.resolveOutputDirectory(join(tmpdir(), "reports")), /inside.*tmp/u);
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

test("buildAuditPlan produces the exact smoke and full audit counts", () => {
  const paths = Array.from({ length: 63 }, (_, index) => `/page-${index}/`);
  const full = harness.buildAuditPlan(paths, "full", BASE_URL);
  assert.equal(full.length, 174);
  assert.equal(full.filter((audit) => audit.phase === "sitemap").length, 126);
  assert.equal(full.filter((audit) => audit.phase === "stress").length, 48);
  assert.equal(new Set(full.map((audit) => audit.artifact)).size, 174);

  const smoke = harness.buildAuditPlan(paths, "smoke", BASE_URL);
  assert.equal(smoke.length, 4);
  assert.deepEqual(new Set(smoke.map((audit) => audit.formFactor)), new Set(["desktop", "mobile"]));
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
