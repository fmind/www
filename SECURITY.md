# Security

Report vulnerabilities privately via GitHub's Security tab ("Report a vulnerability") or <contact@fmind.dev> with the affected URL/commit, reproduction, and impact. Never include credentials or visitor data in public issues.

## Release policy

CI deployment and manual `mise run deploy` enforce identical gates before Cloud Run routes traffic ([README](README.md#deployment)): fixable HIGH/CRITICAL vulnerabilities and secrets block rollout. The CI deploy job holds the Workload Identity token and reads no BuildKit or Trivy cache writable by other jobs.

Weekly [`security.yml`](.github/workflows/security.yml) scans every serving or tagged revision digest via a separate read-only identity and retains unfiltered advisory artifacts for 30 days. Passing the fixable gate does not imply zero advisories.

Trivy may warn about [fallback severity sources](https://trivy.dev/docs/v0.76/guide/scanner/vulnerability/#severity-selection). `trivy.yaml` sets `ignore-unfixed: true` for blocking gates (while `scripts/scan_deployed.py` exports unfiltered HIGH/CRITICAL evidence with `--config /dev/null --ignorefile /dev/null`), `mise.toml` skips only pip's vendored SBOM (absent from the runtime image) and local tooling directories, and `.trivyignore` records the single reviewed Cloud Run exception (`DS-0026`: Dockerfile `HEALTHCHECK` is ignored by Cloud Run, which probes `/health` via `infra/cloud_run.tf`). Review full findings and package inventory; never add unexplained ignores, narrow severity sources, or silence scanners merely to quiet logs.

## Current advisory review

**Owner:** Médéric Hurier. **Reviewed:** 2026-11-22. **Next review:** 2026-11-29, or immediately on a new fixable finding or runtime change.

- **Candidate base**: `python:3.14.10-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f` applies pending Debian security updates in the runtime stage and passes the fixable vuln/secret gate plus HTTP/MCP smoke tests.
- **Scan delta**: the 2026-11-16 scheduled scan of serving revision `www-fmind-dev-manual-4bbb926d10b5` reported 47 HIGH instances across 11 CVEs. The 2026-11-22 unfiltered scan of the rebuilt candidate image reports 50 HIGH instances across the 12 CVEs below, 0 CRITICAL findings, and no Debian trixie fixes (upstream/unstable fixes do not imply trixie availability).
- **Rollout gate**: every rollout still requires serving-digest evidence.

| Residual advisories                                                        | Application exposure assessment                                                                            |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| OpenSSL: CVE-2026-124709                                                   | Cloud Run terminates TLS/QUIC at Google Front End; Granian serves plain HTTP and never runs a QUIC server. |
| Perl: CVE-2026-9538                                                        | No request path executes Perl or caller-controlled Perl data.                                              |
| SQLite: CVE-2026-119373, CVE-2026-119374, CVE-2026-119379                  | Application never loads SQLite, FTS5 tables, or session changesets.                                        |
| ncurses: CVE-2025-69720                                                    | No request path invokes `infocmp` or processes caller-supplied terminfo.                                   |
| systemd: CVE-2026-16742                                                    | Granian runs directly; `systemd-homed` is unused.                                                          |
| libacl: CVE-2026-54369                                                     | No ACL manipulation of caller trees; runtime assets are root-owned and the process is unprivileged.        |
| util-linux: CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 | No mount helpers, `nsenter`, or mount hooks; image strips setuid/setgid bits.                              |

Recheck the [Debian Security Tracker](https://security-tracker.debian.org/tracker/) and serving scan before relying on these reachability reviews (they are not CVE suppressions).

To renew:

1. Dispatch `gh workflow run security.yml` and record `<run-id>` (or read `gh run list --workflow security.yml --event workflow_dispatch --limit 1 --json databaseId,createdAt` after verifying `createdAt` postdates dispatch).
1. Watch `gh run watch <run-id> --exit-status` (new fixable findings fail the job, but artifacts still upload).
1. Download evidence with `gh run download <run-id> -n deployed-image-advisories -D <temp-dir>` (`digests.txt` lists serving/tagged digests; `<revision>.json` holds unfiltered HIGH/CRITICAL findings).
1. Diff CVEs and counts against the table, recheck the Debian tracker, and update the base digest, counts, and dates above.

## Data and recovery

Analytics omit visitor identifiers (180-day expiry); private Cloud Run logs may hold IPs, user agents, and full URLs (30-day expiry; [README](README.md#analytics-and-privacy)). Portrait masters stay private ([AGENTS.md](AGENTS.md#invariants)): `build:portrait` strips EXIF/XMP/comments while keeping orientation and ICC profiles, verified across download URLs and `/connect.vcf`.

`gs://www-fmind-dev-tfstate` is private, versioned, and enforces public-access prevention and uniform bucket-level access; reverify after migration or recovery. Keep Workload Identity Federation keyless, separate runtime/scanner/deployer roles, and retain the prior qualified digest for rollback. WIF accepts only `main` tokens from GitHub-hosted runners matching numeric repo/owner IDs, and binds each service account to one workflow (`deploy.yml` for deployer, `security.yml` for read-only scanner).
