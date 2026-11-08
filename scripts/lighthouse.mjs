#!/usr/bin/env node

import { spawn } from "node:child_process";
import { constants as fsConstants } from "node:fs";
import { access, lstat, mkdir, readFile, realpath, rename, rm, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const LIGHTHOUSE_VERSION = "13.5.0";
const MAX_SITEMAP_BYTES = 2 * 1024 * 1024;
const AUDIT_TIMEOUT_MS = 150_000;
const MAX_AUDIT_ATTEMPTS = 2;
// A performance-only miss is measured this many times in total and judged by the median.
const PERFORMANCE_RUNS = 3;
const PROCESS_OUTPUT_LIMIT = 64 * 1024;
// A failure reason keeps only the tail of Lighthouse's debug stream, where the cause
// and its stack trace end; the report JSON keeps the full runtimeError.
const FAILURE_DETAIL_LIMIT = 2 * 1024;
const CATEGORIES = ["performance", "accessibility", "best-practices", "seo", "agentic-browsing"];
const FORM_FACTORS = ["desktop", "mobile"];
const REPOSITORY_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TMP_ROOT = join(REPOSITORY_ROOT, "tmp");
const OUTPUT_DIRECTORY = join(TMP_ROOT, "lighthouse");

const PORTFOLIO_PATHS = [
  "/",
  "/connect",
  "/privacy",
  "/articles/",
  "/news/",
  "/sites/",
  "/sites/llm-self-hosting/",
  "/sites/mcp-context-cost/",
];

function usage() {
  return `Usage: node scripts/lighthouse.mjs --base-url <origin> | --allow-sandbox

Run the strict Lighthouse ${LIGHTHOUSE_VERSION} portfolio matrix with the Chromium pinned by Playwright.

Options:
  --base-url <origin>  Candidate origin to audit.
  --allow-sandbox      Load an Ubuntu AppArmor userns profile for the pinned Chromium executable.
  -h, --help           Show this help.

Audits the homepage, contact and privacy pages, archive indexes, and both calculators
in desktop and mobile (16 audits); each page must be listed in the origin's sitemap.
Reports go to tmp/lighthouse/.
Every returned category score must be exactly 1; missing expected categories also fail.
When only performance misses, the audit runs ${PERFORMANCE_RUNS - 1} more times and passes only if the median
performance of the ${PERFORMANCE_RUNS} runs is 1 and every run keeps the other categories at 1; each run keeps its report.
`;
}

function optionValue(argument, name, argv, index) {
  const prefix = `${name}=`;
  if (argument.startsWith(prefix)) return { value: argument.slice(prefix.length), nextIndex: index };
  if (argument !== name) return undefined;
  if (index + 1 >= argv.length || argv[index + 1].startsWith("-")) throw new Error(`${name} requires a value`);
  return { value: argv[index + 1], nextIndex: index + 1 };
}

function parseArguments(argv) {
  const options = { allowSandbox: false, baseUrl: undefined, help: false };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--help" || argument === "-h") {
      options.help = true;
      continue;
    }
    if (argument === "--allow-sandbox") {
      options.allowSandbox = true;
      continue;
    }

    const parsed = optionValue(argument, "--base-url", argv, index);
    if (parsed) {
      if (options.baseUrl !== undefined) throw new Error("--base-url may only be specified once");
      options.baseUrl = parsed.value;
      index = parsed.nextIndex;
      continue;
    }
    throw new Error(`unknown argument: ${argument}`);
  }

  if (options.allowSandbox && options.baseUrl !== undefined) {
    throw new Error("--allow-sandbox cannot be combined with --base-url");
  }
  if (!options.help && !options.allowSandbox && !options.baseUrl) throw new Error("--base-url is required");
  return options;
}

function normalizeBaseUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch (error) {
    throw new Error(`invalid base URL ${JSON.stringify(value)}`, { cause: error });
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("base URL must use http or https");
  }
  if (url.username || url.password) throw new Error("base URL must not contain credentials");
  if (url.pathname !== "/" || url.search || url.hash) {
    throw new Error("base URL must be an origin without a path, query, or fragment");
  }
  return url;
}

function isWithin(parent, candidate) {
  const pathFromParent = relative(parent, candidate);
  return (
    pathFromParent === ""
    || (pathFromParent !== ".." && !pathFromParent.startsWith(`..${sep}`) && !isAbsolute(pathFromParent))
  );
}

async function optionalLstat(path) {
  try {
    return await lstat(path);
  } catch (error) {
    if (error?.code === "ENOENT") return undefined;
    throw new Error(`cannot inspect artifact path ${path}: ${error.message}`, { cause: error });
  }
}

async function validateArtifactDirectoryPath(outputDirectory) {
  const resolvedOutput = resolve(REPOSITORY_ROOT, outputDirectory);
  if (!isWithin(TMP_ROOT, resolvedOutput)) {
    throw new Error("artifact directory must resolve inside this repository's ignored tmp/ directory");
  }
  const realRepository = await realpath(REPOSITORY_ROOT);
  let tmpStat = await optionalLstat(TMP_ROOT);
  if (!tmpStat) {
    // tmp/ is a fixed direct child, so lexical containment is established before creating it.
    await mkdir(TMP_ROOT);
    tmpStat = await lstat(TMP_ROOT);
  }
  if (tmpStat.isSymbolicLink() || !tmpStat.isDirectory()) {
    throw new Error("the repository tmp path must be a real directory, not a symbolic link");
  }

  const realTmp = await realpath(TMP_ROOT);
  if (!isWithin(realRepository, realTmp)) {
    throw new Error("the repository tmp directory resolves outside the repository");
  }

  const target = join(resolvedOutput, "reports");
  const parts = relative(TMP_ROOT, target).split(sep).filter(Boolean);
  let current = TMP_ROOT;
  for (const part of parts) {
    current = join(current, part);
    const currentStat = await optionalLstat(current);
    if (!currentStat) continue;
    if (currentStat.isSymbolicLink()) {
      throw new Error(`artifact directory must not contain symbolic links: ${current}`);
    }
    if (!currentStat.isDirectory()) throw new Error(`artifact path component is not a directory: ${current}`);
    const realCurrent = await realpath(current);
    if (!isWithin(realTmp, realCurrent)) throw new Error(`artifact directory resolves outside tmp: ${current}`);
  }

  return { outputDirectory: resolvedOutput, realTmp };
}

function appendOutput(current, chunk) {
  const combined = current + chunk.toString("utf8");
  return combined.length <= PROCESS_OUTPUT_LIMIT ? combined : combined.slice(-PROCESS_OUTPUT_LIMIT);
}

function processGroupExists(child) {
  if (process.platform === "win32" || child.pid === undefined) return false;
  try {
    process.kill(-child.pid, 0);
    return true;
  } catch (error) {
    if (error?.code === "ESRCH") return false;
    throw error;
  }
}

function signalProcessTree(child, signal) {
  if (process.platform === "win32" || child.pid === undefined) return child.kill(signal);
  try {
    process.kill(-child.pid, signal);
    return true;
  } catch (error) {
    if (error?.code === "ESRCH") return false;
    throw error;
  }
}

function runProcess(
  command,
  arguments_,
  { env = process.env, killGraceMs = 5_000, timeoutMs = 10_000 } = {},
) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, arguments_, {
      cwd: REPOSITORY_ROOT,
      // A dedicated POSIX process group lets a timed-out Lighthouse audit
      // terminate Chromium descendants as well as the Node entry process.
      detached: process.platform !== "win32",
      env,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let settled = false;
    let pendingClose;
    let forceKillSent = false;
    let killTimer;

    const timeout = setTimeout(() => {
      timedOut = true;
      try {
        signalProcessTree(child, "SIGTERM");
      } catch (error) {
        settled = true;
        rejectPromise(error);
        return;
      }
      killTimer = setTimeout(() => {
        forceKillSent = true;
        try {
          signalProcessTree(child, "SIGKILL");
        } catch (error) {
          if (!settled) {
            settled = true;
            rejectPromise(error);
          }
          return;
        }
        if (pendingClose && !settled) {
          settled = true;
          resolvePromise(pendingClose);
        }
      }, killGraceMs);
    }, timeoutMs);
    timeout.unref();

    child.stdout.on("data", (chunk) => {
      stdout = appendOutput(stdout, chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr = appendOutput(stderr, chunk);
    });
    child.once("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (killTimer) clearTimeout(killTimer);
      rejectPromise(error);
    });
    child.once("close", (code, signal) => {
      if (settled) return;
      clearTimeout(timeout);
      const result = { code, signal, stdout, stderr, timedOut };
      if (timedOut && !forceKillSent && processGroupExists(child)) {
        // The direct CLI can exit on SIGTERM while its Chromium descendants
        // ignore it. Keep the kill timer referenced and resolve only after the
        // whole dedicated process group receives SIGKILL.
        pendingClose = result;
        return;
      }
      settled = true;
      if (killTimer) clearTimeout(killTimer);
      resolvePromise(result);
    });
  });
}

function processFailure(command, result) {
  const ending = result.timedOut
    ? "timed out"
    : result.signal
    ? `was terminated by ${result.signal}`
    : `exited with code ${result.code}`;
  const output = stripAnsi(result.stderr.trim() || result.stdout.trim());
  const detail = output.length > FAILURE_DETAIL_LIMIT ? `…${output.slice(-FAILURE_DETAIL_LIMIT)}` : output;
  return detail ? `${command} ${ending}: ${detail}` : `${command} ${ending}`;
}

function stripAnsi(value) {
  // Lighthouse and mise color diagnostics even when captured on some installations.
  return value.replace(/\x1B\[[0-?]*[ -/]*[@-~]/gu, "");
}

async function discoverToolchain() {
  let lighthouse;
  try {
    lighthouse = await runProcess("lighthouse", ["--version"], { timeoutMs: 30_000 });
  } catch (error) {
    throw new Error("cannot execute lighthouse; install/select the pinned mise tool", { cause: error });
  }
  if (lighthouse.code !== 0) throw new Error(processFailure("lighthouse --version", lighthouse));
  const lighthouseVersion = lighthouse.stdout.trim();
  if (lighthouseVersion !== LIGHTHOUSE_VERSION) {
    throw new Error(`Lighthouse ${LIGHTHOUSE_VERSION} is required, got ${JSON.stringify(lighthouseVersion)}`);
  }

  const location = await runProcess("mise", ["where", "npm:playwright"], { timeoutMs: 30_000 });
  if (location.code !== 0) throw new Error(processFailure("mise where npm:playwright", location));
  const playwrightRoot = location.stdout.trim();
  if (!isAbsolute(playwrightRoot) || playwrightRoot.includes("\n")) {
    throw new Error(`mise returned an invalid Playwright installation path: ${JSON.stringify(playwrightRoot)}`);
  }

  const packageJsonPath = join(playwrightRoot, "node_modules", "playwright", "package.json");
  const packageJson = JSON.parse(await readFile(packageJsonPath, "utf8"));
  if (typeof packageJson.version !== "string") throw new Error("Playwright package version is missing");

  const playwrightPath = join(playwrightRoot, "node_modules", "playwright", "index.js");
  const playwrightModule = await import(pathToFileURL(playwrightPath).href);
  const playwright = playwrightModule.default ?? playwrightModule;
  const chromiumPath = playwright.chromium?.executablePath();
  if (typeof chromiumPath !== "string" || !isAbsolute(chromiumPath)) {
    throw new Error("the pinned Playwright package did not expose a Chromium executable path");
  }
  try {
    await access(chromiumPath, fsConstants.X_OK);
  } catch (error) {
    throw new Error("pinned Playwright Chromium is not installed; run playwright install chromium", { cause: error });
  }

  return {
    lighthouseVersion,
    playwrightVersion: packageJson.version,
    chromiumPath,
  };
}

function decodeXmlText(value) {
  const entities = { amp: "&", apos: "'", gt: ">", lt: "<", quot: "\"" };
  const decoded = value.replace(/&(amp|apos|gt|lt|quot);/gu, (_, name) => entities[name]);
  if (/&(?:#|[A-Za-z])/u.test(decoded)) throw new Error(`unsupported XML entity in sitemap location: ${value}`);
  return decoded;
}

function parseSitemapPaths(xml, baseUrl) {
  const document = xml.replace(/^\uFEFF/u, "").trim();
  const rootCount = document.match(/<urlset(?:\s|>)/gu)?.length ?? 0;
  const closingRootCount = document.match(/<\/urlset>/gu)?.length ?? 0;
  if (
    rootCount !== 1
    || closingRootCount !== 1
    || !/^(?:<\?xml[^?]*\?>\s*)?<urlset(?:\s[^>]*)?>[\s\S]*<\/urlset>$/u.test(document)
  ) {
    throw new Error("sitemap does not contain a complete urlset root");
  }
  const locations = [...xml.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/gu)].map((match) => decodeXmlText(match[1]));
  if (locations.length === 0) throw new Error("sitemap contains no locations");

  const paths = [];
  const seen = new Set();
  let sitemapOrigin;
  for (const location of locations) {
    if (/[\u0000-\u0020\u007F]/u.test(location)) {
      throw new Error(`sitemap location contains whitespace or control characters: ${JSON.stringify(location)}`);
    }
    let canonical;
    try {
      canonical = new URL(location);
    } catch (error) {
      throw new Error(`invalid sitemap location: ${JSON.stringify(location)}`, { cause: error });
    }
    if (canonical.protocol !== "http:" && canonical.protocol !== "https:") {
      throw new Error(`sitemap location must use http or https: ${canonical.href}`);
    }
    if (canonical.username || canonical.password || canonical.search || canonical.hash) {
      throw new Error(`sitemap location must be a credential-free, query-free page URL: ${canonical.href}`);
    }
    sitemapOrigin ??= canonical.origin;
    if (canonical.origin !== sitemapOrigin) {
      throw new Error(`cross-origin sitemap location rejected: ${canonical.href}`);
    }
    if (!["/agents", "/connect", "/privacy"].includes(canonical.pathname) && !canonical.pathname.endsWith("/")) {
      throw new Error(`sitemap page path must end in a slash: ${canonical.pathname}`);
    }

    // Only the validated path crosses from canonical sitemap data to the selected candidate origin.
    const target = new URL(canonical.pathname, baseUrl);
    if (target.origin !== baseUrl.origin || target.search || target.hash) {
      throw new Error(`sitemap path escaped the candidate origin: ${canonical.pathname}`);
    }
    if (seen.has(target.pathname)) throw new Error(`duplicate sitemap path: ${target.pathname}`);
    seen.add(target.pathname);
    paths.push(target.pathname);
  }

  paths.sort((left, right) => (left < right ? -1 : left > right ? 1 : 0));
  return { paths, sitemapOrigin };
}

async function readSitemapBody(body) {
  if (!body) throw new Error("sitemap response body is missing");

  let reader;
  try {
    reader = body.getReader();
  } catch (error) {
    throw new Error(`cannot read sitemap response body: ${error.message}`, { cause: error });
  }

  const decoder = new TextDecoder("utf-8", { fatal: true });
  let byteLength = 0;
  let xml = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) throw new Error("sitemap response body yielded a non-byte chunk");

      // Fetch exposes content-decoded bytes here, so this caps the actual XML rather than its wire encoding.
      byteLength += value.byteLength;
      if (byteLength > MAX_SITEMAP_BYTES) throw new Error(`sitemap exceeds ${MAX_SITEMAP_BYTES} bytes`);
      xml += decoder.decode(value, { stream: true });
    }
    xml += decoder.decode();
    return xml;
  } catch (error) {
    let cancellationError;
    try {
      await reader.cancel(error);
    } catch (caught) {
      cancellationError = caught;
    }
    const message = error instanceof Error ? error.message : String(error);
    if (cancellationError) {
      throw new Error(`failed to read sitemap body (${message}) and cancel its stream: ${cancellationError.message}`, {
        cause: new AggregateError([error, cancellationError]),
      });
    }
    if (message === `sitemap exceeds ${MAX_SITEMAP_BYTES} bytes`) throw error;
    throw new Error(`failed to read sitemap body: ${message}`, { cause: error });
  } finally {
    reader.releaseLock();
  }
}

async function fetchSitemap(baseUrl, fetchImplementation = globalThis.fetch) {
  const sitemapUrl = new URL("/sitemap.xml", baseUrl);
  const signal = AbortSignal.timeout(30_000);
  let response;
  try {
    response = await fetchImplementation(sitemapUrl, {
      headers: { accept: "application/xml, text/xml;q=0.9" },
      redirect: "follow",
      signal,
    });
  } catch (error) {
    throw new Error(`could not fetch sitemap: ${error.message}`, { cause: error });
  }
  const finalUrl = new URL(response.url);
  if (finalUrl.href !== sitemapUrl.href) {
    throw new Error(`cross-origin or unexpected sitemap redirect rejected: ${response.url}`);
  }
  if (!response.ok) throw new Error(`sitemap returned HTTP ${response.status}`);
  const contentType = response.headers.get("content-type") ?? "";
  const mediaType = contentType.split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "application/xml" && mediaType !== "text/xml" && !mediaType.endsWith("+xml")) {
    throw new Error(`sitemap returned unexpected content type ${JSON.stringify(contentType)}`);
  }
  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_SITEMAP_BYTES) {
    throw new Error(`sitemap exceeds ${MAX_SITEMAP_BYTES} bytes`);
  }
  const xml = await readSitemapBody(response.body);
  return parseSitemapPaths(xml, baseUrl);
}

function pathKey(pathname) {
  if (pathname === "/") return "home";
  return pathname.replace(/^\/+|\/+$/gu, "").replace(/[^a-zA-Z0-9]+/gu, "-").toLowerCase();
}

function buildAuditPlan(baseUrl) {
  const audits = [];
  for (const pathname of PORTFOLIO_PATHS) {
    for (const formFactor of FORM_FACTORS) {
      const index = audits.length + 1;
      audits.push({
        index,
        path: pathname,
        url: new URL(pathname, baseUrl).href,
        formFactor,
        artifact: `reports/${String(index).padStart(3, "0")}-${pathKey(pathname)}-${formFactor}.json`,
      });
    }
  }
  return audits;
}

function validateSitemapScope(paths) {
  const available = new Set(paths);
  for (const pathname of PORTFOLIO_PATHS) {
    if (!available.has(pathname)) throw new Error(`required path is missing from sitemap: ${pathname}`);
  }
}

async function prepareArtifactDirectories(outputDirectory) {
  const validated = await validateArtifactDirectoryPath(outputDirectory);
  await mkdir(validated.outputDirectory, { recursive: true });
  const reportsDirectory = join(validated.outputDirectory, "reports");
  // Report names come from the plan index, so reports of an earlier plan would
  // otherwise sit beside current ones. The path above holds no symbolic link.
  await rm(reportsDirectory, { recursive: true, force: true });
  await mkdir(reportsDirectory, { recursive: true });

  const [realOutput, realReports] = await Promise.all([
    realpath(validated.outputDirectory),
    realpath(reportsDirectory),
  ]);
  if (!isWithin(validated.realTmp, realOutput) || !isWithin(realOutput, realReports)) {
    throw new Error("artifact directory resolves outside this repository's ignored tmp/ directory");
  }
  return { outputDirectory: realOutput, reportsDirectory: realReports };
}

async function writeTextAtomic(filename, contents) {
  const temporary = `${filename}.tmp`;
  await rm(temporary, { force: true });
  await writeFile(temporary, contents, { encoding: "utf8", flag: "wx" });
  await rename(temporary, filename);
}

async function writeJsonAtomic(filename, value) {
  await writeTextAtomic(filename, `${JSON.stringify(value, null, 2)}\n`);
}

function comparableUrl(value) {
  try {
    return new URL(value);
  } catch {
    return undefined;
  }
}

function inspectReport(report, audit, baseUrl) {
  const errors = [];
  const scores = {};
  if (!report || typeof report !== "object" || Array.isArray(report)) {
    return { errors: ["Lighthouse output is not a JSON object"], scores };
  }
  if (report.lighthouseVersion !== LIGHTHOUSE_VERSION) {
    errors.push(`report Lighthouse version is ${JSON.stringify(report.lighthouseVersion)}`);
  }
  if (report.runtimeError) errors.push(`Lighthouse runtime error: ${JSON.stringify(report.runtimeError)}`);

  const requested = comparableUrl(report.requestedUrl);
  const final = comparableUrl(report.finalDisplayedUrl ?? report.finalUrl);
  const expected = new URL(audit.url);
  if (!requested || requested.href !== expected.href) {
    errors.push(`report requested URL does not match ${expected.href}`);
  }
  if (
    !final
    || final.origin !== baseUrl.origin
    || final.pathname !== expected.pathname
    || final.search !== expected.search
    || final.hash
  ) {
    errors.push(`report final URL escaped or changed the audited page: ${final?.href ?? "missing"}`);
  }

  const categories = report.categories;
  if (!categories || typeof categories !== "object" || Array.isArray(categories)) {
    errors.push("report categories are missing or invalid");
    return { errors, scores };
  }
  const expectedCategories = new Set(CATEGORIES);
  for (const category of Object.keys(categories)) {
    if (!expectedCategories.has(category)) errors.push(`unexpected category: ${category}`);
  }
  for (const category of CATEGORIES) {
    if (!Object.hasOwn(categories, category)) {
      errors.push(`expected category is missing: ${category}`);
      continue;
    }
    const result = categories[category];
    const score = result && typeof result === "object" ? result.score : undefined;
    scores[category] = score ?? null;
    if (score !== 1) errors.push(`${category} score is ${JSON.stringify(score)}, expected 1`);
  }
  return { errors, scores };
}

async function runLighthouse(audit, artifact, baseUrl, artifactDirectories, toolchain, runProcessImplementation) {
  const reportPath = join(artifactDirectories.outputDirectory, artifact);
  const temporaryPath = `${reportPath}.tmp`;

  const arguments_ = [
    audit.url,
    "--output=json",
    `--output-path=${temporaryPath}`,
    `--only-categories=${CATEGORIES.join(",")}`,
    "--chrome-flags=--headless=new",
    "--no-enable-error-reporting",
    "--disable-full-page-screenshot",
    "--locale=en-US",
    "--max-wait-for-load=45000",
  ];
  if (audit.formFactor === "desktop") arguments_.push("--preset=desktop");

  let lastRun;
  for (let attempt = 1; attempt <= MAX_AUDIT_ATTEMPTS; attempt += 1) {
    await rm(reportPath, { force: true });
    await rm(temporaryPath, { force: true });

    let processResult;
    try {
      processResult = await runProcessImplementation("lighthouse", arguments_, {
        env: {
          ...process.env,
          CHROME_PATH: toolchain.chromiumPath,
          FORCE_COLOR: "0",
          NO_COLOR: "1",
        },
        timeoutMs: AUDIT_TIMEOUT_MS,
      });
    } catch (error) {
      return { passed: false, scores: {}, errors: [`could not execute Lighthouse: ${error.message}`], artifact: null };
    }

    const executionErrors = processResult.code === 0 ? [] : [processFailure("lighthouse", processResult)];
    let report;
    try {
      report = JSON.parse(await readFile(temporaryPath, "utf8"));
      await rename(temporaryPath, reportPath);
    } catch (error) {
      await rm(temporaryPath, { force: true });
      return {
        passed: false,
        scores: {},
        errors: [...executionErrors, `Lighthouse did not produce valid JSON: ${error.message}`],
        artifact: null,
      };
    }

    const inspected = inspectReport(report, audit, baseUrl);
    const errors = [...executionErrors, ...inspected.errors];
    lastRun = { passed: errors.length === 0, scores: inspected.scores, errors, artifact };
    if (lastRun.passed || report?.runtimeError?.code !== "NO_NAVSTART") return lastRun;
  }

  return lastRun;
}

function isPerformanceOnlyMiss(run) {
  // A run lists every failed check, so a single error with a numeric performance score
  // below 1 and every other category at exactly 1 can only be the performance score.
  const performance = run.scores.performance;
  return (
    run.errors.length === 1
    && typeof performance === "number"
    && performance < 1
    && CATEGORIES.every((category) => category === "performance" || run.scores[category] === 1)
  );
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)];
}

function formatScores(scores) {
  return scores.map((score) => JSON.stringify(score)).join(", ");
}

async function runAudit(audit, baseUrl, artifactDirectories, toolchain, runProcessImplementation = runProcess) {
  const first = await runLighthouse(
    audit,
    audit.artifact,
    baseUrl,
    artifactDirectories,
    toolchain,
    runProcessImplementation,
  );
  if (first.passed || !isPerformanceOnlyMiss(first)) return { ...audit, ...first };

  // Performance alone varies between consecutive runs, so a performance-only miss is
  // judged by the median of PERFORMANCE_RUNS runs. Every other category must still be
  // exactly 1 in each run, and every run keeps its own report.
  const runs = [first];
  for (let run = 2; run <= PERFORMANCE_RUNS; run += 1) {
    const artifact = audit.artifact.replace(/\.json$/u, `-performance-run-${run}.json`);
    runs.push(await runLighthouse(audit, artifact, baseUrl, artifactDirectories, toolchain, runProcessImplementation));
  }
  const performanceRuns = runs.map((run) => ({ artifact: run.artifact, score: run.scores.performance ?? null }));
  const scores = performanceRuns.map((run) => run.score);
  const invalidRuns = runs.flatMap((run, offset) =>
    run.passed || isPerformanceOnlyMiss(run)
      ? []
      : run.errors.map((error) => `performance run ${offset + 1}: ${error}`)
  );
  const performanceMedian = invalidRuns.length === 0 ? median(scores) : null;
  let errors = [];
  if (invalidRuns.length > 0) {
    errors = [`performance runs ${formatScores(scores)} have no valid median`, ...invalidRuns];
  } else if (performanceMedian !== 1) {
    errors = [`performance median is ${performanceMedian} over runs ${formatScores(scores)}, expected 1`];
  }

  return {
    ...audit,
    passed: errors.length === 0,
    scores: { ...first.scores, performance: performanceMedian ?? first.scores.performance },
    errors,
    artifact: first.artifact,
    performanceRuns,
    performanceMedian,
  };
}

function summarize(manifest, results, status) {
  const categorySummary = {};
  for (const category of CATEGORIES) {
    const scores = results.map((result) => result.scores[category]).filter((score) => typeof score === "number");
    categorySummary[category] = {
      observed: scores.length,
      perfect: scores.filter((score) => score === 1).length,
      minimum: scores.length > 0 ? Math.min(...scores) : null,
    };
  }
  const failures = results
    .filter((result) => !result.passed)
    .map((result) => ({
      index: result.index,
      path: result.path,
      formFactor: result.formFactor,
      artifact: result.artifact,
      errors: result.errors,
      performanceRuns: result.performanceRuns,
    }));
  const performanceReruns = results
    .filter((result) => result.performanceRuns)
    .map((result) => ({
      index: result.index,
      path: result.path,
      formFactor: result.formFactor,
      passed: result.passed,
      performanceMedian: result.performanceMedian,
      performanceRuns: result.performanceRuns,
    }));

  return {
    schemaVersion: 1,
    status,
    baseUrl: manifest.baseUrl,
    lighthouseVersion: manifest.lighthouseVersion,
    playwrightVersion: manifest.playwrightVersion,
    chromiumPath: manifest.chromiumPath,
    categories: categorySummary,
    plannedAudits: manifest.audits.length,
    completedAudits: results.length,
    passedAudits: results.filter((result) => result.passed).length,
    failedAudits: failures.length,
    failures,
    performanceReruns,
    results,
  };
}

function describeFailure(failure) {
  const reason = failure.errors.join("; ").replaceAll("\n", " ");
  return `${failure.index}: ${failure.formFactor} ${failure.path} — ${reason}`;
}

function describePerformanceRuns(audit) {
  const scores = formatScores(audit.performanceRuns.map((run) => run.score));
  const verdict = audit.passed ? "passed" : "failed";
  return `${audit.index}: ${audit.formFactor} ${audit.path} — performance runs ${scores}; median ${
    audit.performanceMedian ?? "n/a"
  }; ${verdict}`;
}

function renderSummary(summary) {
  const lines = [
    "# Lighthouse qualification summary",
    "",
    `- Status: **${summary.status}**`,
    `- Base URL: ${summary.baseUrl}`,
    `- Completed: ${summary.completedAudits}/${summary.plannedAudits}`,
    `- Passed: ${summary.passedAudits}`,
    `- Failed: ${summary.failedAudits}`,
    "",
    "| Category | Perfect / observed | Minimum |",
    "| --- | ---: | ---: |",
  ];
  for (const [category, result] of Object.entries(summary.categories)) {
    lines.push(`| ${category} | ${result.perfect} / ${result.observed} | ${result.minimum ?? "n/a"} |`);
  }
  if (summary.performanceReruns.length > 0) {
    lines.push(
      "",
      "## Performance medians",
      "",
      `Only performance missed 1 in these audits, so each ran ${PERFORMANCE_RUNS} times and the table above counts the median.`,
      "",
    );
    for (const audit of summary.performanceReruns) {
      lines.push(`- ${describePerformanceRuns(audit).replaceAll("|", "\\|")}`);
    }
  }
  if (summary.failures.length > 0) {
    lines.push("", "## Failures", "");
    for (const failure of summary.failures) lines.push(`- ${describeFailure(failure).replaceAll("|", "\\|")}`);
  }
  return `${lines.join("\n")}\n`;
}

async function writeSummary(outputDirectory, manifest, results, status) {
  const summary = summarize(manifest, results, status);
  await Promise.all([
    writeJsonAtomic(join(outputDirectory, "summary.json"), summary),
    writeTextAtomic(join(outputDirectory, "summary.md"), renderSummary(summary)),
  ]);
  return summary;
}

async function allowChromiumSandbox(
  chromiumPath,
  { outputDirectory = OUTPUT_DIRECTORY, runProcessImplementation = runProcess } = {},
) {
  if (typeof chromiumPath !== "string" || !isAbsolute(chromiumPath) || !/^\/[A-Za-z0-9._/-]+$/u.test(chromiumPath)) {
    throw new Error(`invalid Chromium executable path: ${JSON.stringify(chromiumPath)}`);
  }
  await access(chromiumPath, fsConstants.X_OK);
  const validated = await validateArtifactDirectoryPath(outputDirectory);
  await mkdir(validated.outputDirectory, { recursive: true });
  const profilePath = join(validated.outputDirectory, "www-lighthouse-chromium.apparmor");
  const destination = "/etc/apparmor.d/www-lighthouse-chromium";
  const profile = [
    "abi <abi/4.0>,",
    "include <tunables/global>",
    `profile www-lighthouse-chromium "${chromiumPath}" flags=(unconfined) {`,
    "  userns,",
    "}",
    "",
  ].join("\n");
  await writeTextAtomic(profilePath, profile);
  try {
    const installResult = await runProcessImplementation("sudo", ["install", "-m", "0644", profilePath, destination]);
    if (installResult.code !== 0) throw new Error(processFailure("sudo install apparmor profile", installResult));
    const parserResult = await runProcessImplementation("sudo", ["apparmor_parser", "-r", destination]);
    if (parserResult.code !== 0) throw new Error(processFailure("sudo apparmor_parser", parserResult));
  } finally {
    await rm(profilePath, { force: true });
  }
}

async function run() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }
  if (options.allowSandbox) {
    const toolchain = await discoverToolchain();
    await allowChromiumSandbox(toolchain.chromiumPath);
    return;
  }

  const baseUrl = normalizeBaseUrl(options.baseUrl);
  const toolchain = await discoverToolchain();
  const sitemap = await fetchSitemap(baseUrl);
  validateSitemapScope(sitemap.paths);
  const audits = buildAuditPlan(baseUrl);
  const artifactDirectories = await prepareArtifactDirectories(OUTPUT_DIRECTORY);
  const manifest = {
    schemaVersion: 1,
    baseUrl: baseUrl.href,
    sitemapUrl: new URL("/sitemap.xml", baseUrl).href,
    sitemapOrigin: sitemap.sitemapOrigin,
    lighthouseVersion: toolchain.lighthouseVersion,
    playwrightVersion: toolchain.playwrightVersion,
    chromiumPath: toolchain.chromiumPath,
    categories: CATEGORIES,
    sitemapPaths: sitemap.paths,
    portfolioPaths: PORTFOLIO_PATHS,
    audits,
  };
  await writeJsonAtomic(join(artifactDirectories.outputDirectory, "plan.json"), manifest);

  const results = [];
  await writeSummary(artifactDirectories.outputDirectory, manifest, results, "running");
  for (const audit of audits) {
    process.stdout.write(
      `[${audit.index}/${audits.length}] ${audit.formFactor}: ${audit.path}\n`,
    );
    const result = await runAudit(audit, baseUrl, artifactDirectories, toolchain);
    if (result.performanceRuns) process.stdout.write(`  ${describePerformanceRuns(result)}\n`);
    results.push(result);
    await writeSummary(artifactDirectories.outputDirectory, manifest, results, "running");
  }

  const failed = results.some((result) => !result.passed);
  const summary = await writeSummary(
    artifactDirectories.outputDirectory,
    manifest,
    results,
    failed ? "failed" : "passed",
  );
  process.stdout.write(
    `Lighthouse qualification ${summary.status}: ${summary.passedAudits}/${summary.plannedAudits} audits passed.\n`,
  );
  if (failed) {
    // Name each failed page and category in the log, not only in the uploaded artifact.
    for (const failure of summary.failures) {
      process.stderr.write(`lighthouse harness: failed ${describeFailure(failure)}\n`);
    }
    throw new Error(`strict Lighthouse qualification failed in ${summary.failedAudits} audit(s)`);
  }
}

// import.meta.main also holds when Node runs this file through a symbolic link.
if (import.meta.main) {
  run().catch((error) => {
    process.stderr.write(`lighthouse harness: ${error.message}\n`);
    process.exitCode = 1;
  });
}

export {
  allowChromiumSandbox,
  buildAuditPlan,
  describeFailure,
  fetchSitemap,
  inspectReport,
  LIGHTHOUSE_VERSION,
  normalizeBaseUrl,
  parseArguments,
  parseSitemapPaths,
  prepareArtifactDirectories,
  renderSummary,
  runAudit,
  runProcess,
  summarize,
  validateSitemapScope,
};
