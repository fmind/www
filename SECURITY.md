# Security

Report suspected vulnerabilities privately to <contact@fmind.dev>, with the affected URL or commit, reproduction steps, and expected impact. Do not include credentials or visitor data in public issues.

## Verification policy

The deployment gate scans and smoke-tests the pushed immutable image before Cloud Run receives it. HIGH/CRITICAL vulnerabilities with an available fix and secret findings block rollout. A passing filtered gate does not mean that the image has no advisories.

The weekly [security workflow](.github/workflows/security.yml) resolves every Cloud Run revision receiving traffic and scans its exact platform digest, including unfixed HIGH/CRITICAL vulnerabilities. Its `deployed-image-advisories` artifact retains the traffic snapshot, revision-to-digest mapping, and JSON reports for 30 days. A separate read-only identity has service-level Cloud Run viewer and repository-level Artifact Registry reader grants. It cannot deploy or impersonate the runtime identity.

**Review owner:** Médéric Hurier. **Last reviewed:** 2026-09-14 (local candidate and hosted deployed-image evidence). **Next review:** 2026-09-21, or immediately after a new fixable finding or a runtime/dependency change that affects reachability. Recheck scanner reports, Debian status, the maintained base image, and request-path applicability; rebuild and qualify an updated image when a fix becomes available. No CVE suppression was added for these findings.

## Local candidate scan — 2026-09-13

The local website candidate built from `python:3.14.7-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6` failed `mise run check:image`: Trivy reported 12 fixable Debian findings (9 HIGH, 3 CRITICAL) across `gzip`, `libpcre2-8-0`, `libsqlite3-0`, and `perl-base`. Python dependency checks passed. A fresh registry lookup of `python:3.14.7-slim` still resolved to the same pinned digest. The Dockerfile now pins the available fixes: `gzip=1.13-1+deb13u1`, `libpcre2-8-0=10.46-1~deb13u2`, `libsqlite3-0=3.46.1-7+deb13u2`, and `perl-base=5.40.1-6+deb13u1`. Remove this patch layer when a refreshed upstream digest includes the fixes. No advisory suppression was added; the image must pass its normal scan and runtime smoke test before release. This is local candidate evidence, not a new scan of deployed revisions; the dated deployed baseline below remains separate.

## Local review — 2026-09-14

The reviewed local application image passes the fixable HIGH/CRITICAL vulnerability gate and the production HTTP/MCP smoke test after the pinned Debian patch layer and the MCP 2.2.0 dependency update. An additional unfiltered HIGH/CRITICAL scan found 44 package/advisory instances covering 8 unique CVEs, all HIGH and without an available fix; there were no CRITICAL findings. Local Google Cloud credentials require interactive reauthentication, so deployed verification uses the existing read-only hosted workflow.

The [2026-09-14 hosted security run](https://github.com/fmind/www/actions/runs/34824997460) independently scanned the serving platform digest `sha256:56c6945c32b78f69a4bfda766e1278f954688b8fd8f59dfb01e65d2710af4a37`, with revision `www-fmind-dev-00042-nnj` receiving 100% of traffic. Its retained report found the same 44 HIGH instances across 8 CVEs, no CRITICAL findings, and no available fixes. This is the pre-release baseline; rerun the hosted workflow after deployment to capture the new serving digest. The older assessment below remains historical.

## Pre-deployment verification — 2026-09-14

The direct `mise run check:image:deployed` review of revision `www-fmind-dev-00043-2t9`, receiving 100% of traffic, scanned platform digest `sha256:8c3ffaed9ada9a848f6b98ad8c6cceb543e6938b28e7bcea5dc50ff58feeec48`. It passed the fixable vulnerability and secret gates; the unfiltered report contained 44 HIGH package/advisory instances across 8 CVEs, no CRITICAL findings, and no available fixes. This is a dated snapshot before the portfolio review deployment, not evidence for a later revision. Recheck the serving digest after rollout.

## Historical package exposure — 2026-09-07

The 2026-09-07 review scanned platform digest `sha256:358f3f22a66a1bd5f7170f06c00e9d5e76b27710851aea2cb46340247a215938` in `europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev`. It found 54 Debian package/advisory instances (51 HIGH, 3 CRITICAL), covering 18 unique CVEs, with no fixed version reported and no HIGH/CRITICAL Python-package finding. This is a dated baseline; the workflow artifact identifies what is serving at each subsequent scan.

The table records source-based reachability assessment, not exploit testing or a claim that affected libraries are absent. The runtime is amd64, non-root, has no database, and does not launch external commands from request handlers. Public requests cannot upload archives, databases, terminal descriptions, or filesystem ACLs. Authored content and dependencies remain separate trusted build inputs.

| Component and advisories                                                                                                           | Reviewed applicability and remaining boundary                                                                                                                                                                                                              |
| ---------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Perl: CVE-2026-13221, CVE-2026-8376, CVE-2026-42496, CVE-2026-42497, CVE-2026-48962, CVE-2026-57432, CVE-2026-57433, CVE-2026-9538 | No request path invokes Perl regex compilation, archive extraction, compression output globs, pack/unpack, or Storable. CVE-2026-8376 specifically concerns 32-bit builds; the image is amd64. Reassess if subprocess or archive processing is introduced. |
| SQLite: CVE-2026-11822, CVE-2026-11824                                                                                             | No database or SQLite FTS5 usage in the application. Reassess before adding a database or accepting database files.                                                                                                                                        |
| ncurses: CVE-2025-69720                                                                                                            | No interactive terminal or caller-supplied terminal database processing in the web service.                                                                                                                                                                |
| systemd: CVE-2026-16742                                                                                                            | The container runs Granian, not systemd-homed. The shared library's presence alone does not establish exposure to the affected home-record workflow.                                                                                                       |
| gzip: CVE-2026-41992                                                                                                               | No request path invokes gzip's LZH decompressor. HTTP Brotli compression uses a separate library.                                                                                                                                                          |
| libacl: CVE-2026-54369                                                                                                             | No ACL manipulation of caller-owned filesystem trees; runtime files are root-owned and the process is unprivileged.                                                                                                                                        |
| util-linux: CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410                                                         | No request path invokes mount helpers, nsenter, or mount post-hooks. The image strips setuid/setgid privileges from installed helpers.                                                                                                                     |

Consult the [Debian Security Tracker](https://security-tracker.debian.org/tracker/) for release-specific status. Package severity alone does not establish website exploitability. The three CRITICAL entries concern [large Perl regular expressions](https://security-tracker.debian.org/tracker/CVE-2026-13221), [Archive::Tar symlinks](https://security-tracker.debian.org/tracker/CVE-2026-42496), and [32-bit Perl regular expressions](https://security-tracker.debian.org/tracker/CVE-2026-8376).

## Logs and privacy

Custom analytics omit visitor identifiers and IP addresses and expire from BigQuery after 180 days. Private Cloud Run operational request logs are separate and can include IP addresses, user agents, and full request URLs; the Cloud Logging `_Default` bucket retains them for 30 days. See [README analytics](README.md#analytics) for the data-flow scope.
