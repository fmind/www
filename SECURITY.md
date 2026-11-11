# Security

Report vulnerabilities privately via GitHub's Security tab ("Report a vulnerability") or <contact@fmind.dev> with the affected URL/commit, reproduction, and impact. Never include credentials or visitor data in public issues.

## Release policy

CI deployment and manual `mise run deploy` enforce identical gates before Cloud Run routes traffic ([README](README.md#deployment)): fixable HIGH/CRITICAL vulnerabilities and secrets block rollout. The CI deploy job holds the Workload Identity token and reads no BuildKit or Trivy cache writable by other jobs. Weekly [`security.yml`](.github/workflows/security.yml) scans every serving or tagged revision digest via a separate read-only identity and retains unfiltered advisory artifacts for 30 days. Passing the fixable gate does not imply zero advisories.

Trivy may warn about [fallback severity sources](https://trivy.dev/docs/v0.76/guide/scanner/vulnerability/#severity-selection). `mise.toml` skips only pip's vendored SBOM (absent from the runtime image). Review full findings and package inventory; never add ignores, narrow severity sources, or silence scanners merely to quiet logs.

## Current advisory review

**Owner:** Médéric Hurier. **Reviewed:** 2026-11-10. **Next review:** 2026-11-17, or immediately on a new fixable finding or runtime change.

Candidate base image `python:3.14.10-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d` applies pending Debian security updates in its runtime stage and passes the fixable vuln/secret gate plus HTTP/MCP smoke tests. The 2026-11-10 unfiltered scan of the serving revision reports 47 Trivy HIGH instances across the 11 CVEs below, 0 CRITICAL findings, and no available Debian trixie fixes (upstream/unstable fixes do not imply trixie availability). Every rollout still requires serving-digest evidence.

| Residual advisories                                                        | Application exposure assessment                                                                     |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Perl: CVE-2026-9538                                                        | No request path executes Perl or caller-controlled Perl data.                                       |
| SQLite: CVE-2026-119373, CVE-2026-119374, CVE-2026-119379                  | Application never loads SQLite, FTS5 tables, or session changesets.                                 |
| ncurses: CVE-2025-69720                                                    | No request path invokes `infocmp` or processes caller-supplied terminfo.                            |
| systemd: CVE-2026-16742                                                    | Granian runs directly; `systemd-homed` is unused.                                                   |
| libacl: CVE-2026-54369                                                     | No ACL manipulation of caller trees; runtime assets are root-owned and the process is unprivileged. |
| util-linux: CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 | No mount helpers, `nsenter`, or mount hooks; image strips setuid/setgid bits.                       |

Recheck the [Debian Security Tracker](https://security-tracker.debian.org/tracker/) and serving scan before relying on these reachability reviews (they are not CVE suppressions).

To renew: dispatch `gh workflow run security.yml` and capture `<run-id>` (or take `gh run list --workflow security.yml --event workflow_dispatch --limit 1 --json databaseId,createdAt` only if `createdAt` postdates dispatch). Watch `gh run watch <run-id> --exit-status` (failures may reflect new fixable findings; artifacts still upload), then run `gh run download <run-id> -n deployed-image-advisories -D <temp-dir>` (`digests.txt` lists serving/tagged digests; `<revision>.json` holds unfiltered HIGH/CRITICAL findings). Diff CVEs/counts against the table, recheck Debian tracker, and update the base digest, counts, and dates above.

## Data and recovery

Analytics omit visitor identifiers (180-day expiry); private Cloud Run logs may hold IPs, user agents, and full URLs (30-day expiry; [README](README.md#analytics-and-privacy)). Portrait masters stay private ([AGENTS.md](AGENTS.md#invariants)): `build:portrait` strips EXIF/XMP/comments while keeping orientation and ICC profiles, verified across download URLs and `/connect.vcf`.

`gs://www-fmind-dev-tfstate` is private, versioned, and enforces public-access prevention and uniform bucket-level access—reverify after migration or recovery. Keep Workload Identity Federation keyless, separate runtime/scanner/deployer roles, and retain the prior qualified digest for rollback. WIF accepts only `main` tokens from GitHub-hosted runners matching numeric repo/owner IDs, and binds each service account to one workflow (`deploy.yml` for deployer, `security.yml` for read-only scanner).
