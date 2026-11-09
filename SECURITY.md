# Security

Report vulnerabilities privately to <contact@fmind.dev> with the affected URL/commit, reproduction, and impact. Do not include credentials or visitor data in issues.

## Release policy

CI deployment and the manual `mise run deploy` pass the same gates before Cloud Run routes traffic ([README](README.md#deployment)). Fixable HIGH/CRITICAL vulnerabilities and secrets block rollout. The CI deploy job holds the Workload Identity token, so it reads no BuildKit or Trivy cache that another job could write. The weekly [security workflow](.github/workflows/security.yml) scans every serving or tagged revision digest through a separate read-only identity and retains unfiltered advisory evidence for 30 days. Passing the filtered gate does not mean zero advisories.

Trivy may warn about [fallback severity sources](https://trivy.dev/docs/v0.76/guide/scanner/vulnerability/#severity-selection). `mise.toml` skips only pip's vendored SBOM, which is absent from the final image (justified there). Review the full findings and package inventory; do not add other silences, narrow severity sources, or add ignores merely to produce a quiet log.

## Current advisory review

**Owner:** Médéric Hurier. **Reviewed:** 2026-11-07. **Next review:** 2026-11-14, or immediately on a new fixable finding or relevant runtime change.

The current candidate uses `python:3.14.10-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d`, and its runtime stage applies pending Debian security updates because they can lag the base image. The fixable vulnerability/secret gate and HTTP/MCP image smoke pass. The November 7 unfiltered scan of the single serving/tagged revision image (built on that base digest) reports 49 Trivy HIGH package/advisory instances across the 13 CVEs below, no CRITICAL findings, and no fixes available for the installed Debian trixie packages. Upstream and Debian unstable fixes exist; their availability does not imply a compatible trixie update. Each new rollout still needs its own serving-digest evidence.

| Residual advisories                                                        | Application exposure assessment                                                                           |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Perl: CVE-2026-9538                                                        | No request path executes Perl or caller-controlled Perl data.                                             |
| SQLite: CVE-2026-119373, CVE-2026-119374, CVE-2026-119379                  | The application never loads SQLite, creates no FTS5 tables, and applies no session changesets.            |
| zlib: CVE-2026-76844, CVE-2026-85091                                       | Debian marks the installed trixie-security build (`+deb13u1`) fixed; Trivy's data still flags it.         |
| ncurses: CVE-2025-69720                                                    | No request path invokes infocmp or processes caller-supplied terminfo.                                    |
| systemd: CVE-2026-16742                                                    | Granian runs directly; the service does not run systemd-homed.                                            |
| libacl: CVE-2026-54369                                                     | No ACL manipulation of caller-owned trees; runtime assets are root-owned and the process is unprivileged. |
| util-linux: CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 | No request path invokes mount helpers, nsenter, or mount post-hooks; the image strips setuid/setgid bits. |

Recheck the [Debian Security Tracker](https://security-tracker.debian.org/tracker/) and exact serving scan before relying on these assessments. They are reachability reviews, not CVE suppressions. Retired scan histories remain in Git history; CI advisory artifacts expire after 30 days.

To renew this review, run `gh workflow run security.yml` and take `<run-id>` from the run URL it prints. If it prints none, use the run from `gh run list --workflow security.yml --event workflow_dispatch --limit 1 --json databaseId,createdAt` only when its `createdAt` is later than your dispatch; an older run holds stale evidence. Wait with `gh run watch <run-id> --exit-status`: a failure can be a new fixable finding, and the evidence is still uploaded. Then run `gh run download <run-id> -n deployed-image-advisories -D <temporary-directory>`. Its `digests.txt` lists each serving or tagged revision digest, and `<revision>.json` holds that image's unfiltered HIGH/CRITICAL findings. Compare the CVE and instance set with the table, recheck the Debian tracker, then update the base digest, counts, and dates above.

## Data and recovery

Analytics omit visitor identifiers and expire after 180 days. Private Cloud Run operational logs can contain IPs, user agents, and full URLs and expire after 30 days. See [README](README.md#analytics-and-privacy).

Portrait masters stay private ([AGENTS.md](AGENTS.md#invariants)): `build:portrait` removes EXIF/XMP/comments while retaining orientation and ICC color, and tests inspect both download URLs and the vCard portrait.

The state bucket is private, versioned, and protected by public-access prevention; verify those bootstrap settings after migration or recovery. Use keyless Workload Identity Federation, keep runtime/scanner/deployer roles separate, and retain the preceding qualified image digest for rollback. Federation accepts only `main` tokens from GitHub-hosted runners and the numeric repository/owner IDs, and each service account trusts one workflow file: only `deploy.yml` can assume the deployer and only `security.yml` the read-only scanner, so no other workflow on `main` inherits deploy rights.
