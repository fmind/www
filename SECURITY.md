# Security

Report vulnerabilities privately to <contact@fmind.dev> with the affected URL/commit, reproduction, and impact. Do not include credentials or visitor data in public issues.

## Release policy

Deployment scans and smoke-tests the pushed immutable digest before Cloud Run receives it, then verifies the new revision on a no-traffic tagged URL before promoting that exact revision. Fixable HIGH/CRITICAL vulnerabilities and secrets block rollout. The weekly [security workflow](.github/workflows/security.yml) scans every serving digest through a separate read-only identity and retains unfiltered advisory evidence for 30 days. Passing the filtered gate does not mean zero advisories.

Trivy may warn about third-party SBOM metadata or [fallback severity sources](https://trivy.dev/docs/v0.74/guide/scanner/vulnerability/#severity-selection). Review the full findings and package inventory; do not silence diagnostics, narrow severity sources, or add ignores merely to produce a quiet log.

## Current advisory review

**Owner:** Médéric Hurier. **Reviewed:** 2026-09-19. **Next review:** 2026-09-26, or immediately on a new fixable finding or relevant runtime change.

The current candidate uses refreshed `python:3.14.7-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2`; upstream now includes the security fixes previously installed by a separate Debian patch layer. The fixable vulnerability/secret gate and HTTP/MCP image smoke pass. The unfiltered scan reports 44 HIGH package/advisory instances across eight CVEs, no CRITICAL findings, and no available fixes. These are candidate results; the deployed-image workflow establishes serving-digest evidence after rollout.

| Residual advisories                                                        | Application exposure assessment                                                                           |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Perl: CVE-2026-9538                                                        | No request path executes Perl or caller-controlled Perl data.                                             |
| ncurses: CVE-2025-69720                                                    | No interactive terminal or caller-supplied terminal database processing.                                  |
| systemd: CVE-2026-16742                                                    | Granian runs directly; the service does not run systemd-homed.                                            |
| libacl: CVE-2026-54369                                                     | No ACL manipulation of caller-owned trees; runtime assets are root-owned and the process is unprivileged. |
| util-linux: CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 | No request path invokes mount helpers, nsenter, or mount post-hooks; the image strips setuid/setgid bits. |

Recheck the [Debian Security Tracker](https://security-tracker.debian.org/tracker/) and exact serving scan before relying on these assessments. They are reachability reviews, not CVE suppressions. Retired scan histories remain in Git history and CI artifacts.

## Data and recovery

Analytics omit visitor identifiers and expire after 180 days. Private Cloud Run operational logs can contain IPs, user agents, and full URLs and expire after 30 days. See [README](README.md#analytics-and-privacy).

Keep private portrait masters outside `static/`; `build:portrait` removes EXIF/XMP/comments while retaining orientation and ICC color. Tests inspect both download URLs and the vCard portrait.

The state bucket is private, versioned, and protected by public-access prevention; verify those bootstrap settings after migration or recovery. Use keyless Workload Identity Federation, keep runtime/scanner/deployer roles separate, and retain the preceding qualified image digest for rollback. Federation accepts only `main` tokens from the numeric repository/owner IDs, and each service account trusts one workflow file: only `deploy.yml` can assume the deployer and only `security.yml` the read-only scanner, so no other workflow on `main` inherits deploy rights.
