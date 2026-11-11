# www

Personal website and portfolio of [Médéric Hurier (Fmind)](https://www.fmind.dev/), freelance AI Architect (AI agents, MLOps, security). Built with Python 3.14, Litestar, strict Jinja, Tailwind CSS v4, DaisyUI v5, and Granian—no client framework, database, or runtime CDN.

Alongside articles, [daily tech news](https://www.fmind.dev/news/), and read-only [agent and MCP endpoints](https://www.fmind.dev/agents) (`/mcp`, `/api/profile`, `/api/news`, `/llms.txt`, `/llms-full.txt`), the site hosts two server-rendered decision tools with native GET forms and MCP tools:

- [LLM hosting budget tool](https://www.fmind.dev/sites/llm-self-hosting/) ([sources](src/www/sites/sources.md)): compares open-weight models on GKE (GPU and Cloud TPU) against managed APIs.
- [MCP context-cost calculator](https://www.fmind.dev/sites/mcp-context-cost/) ([sources](src/www/sites/mcp_context_cost/sources.md)): estimates token and input-cost overhead from measured MCP servers (GitHub, Filesystem, Memory, Playwright).

## Development

Requires [mise](https://mise.jdx.dev/) and Docker Engine with Buildx (no cloud credentials). `mise.toml`, `mise.lock`, and `.mise/locks/` pin the toolchain and transitive npm dependencies.

```bash
mise install && mise run install && mise run watch
```

Open `http://localhost:8080` (`PORT=8081` overrides the port; `GRANIAN_HOST=0.0.0.0` opts in to LAN access). `uv run --locked www` runs the production entrypoint (`HOST=127.0.0.1` by default, `0.0.0.0` in the container). See [`.env.example`](.env.example) for runtime variables (`.env` is not auto-loaded) and [AGENTS.md](AGENTS.md) for architecture and `.agents/skills/` workflows.

## Tasks

`mise.toml` defines the task contract for local work, hooks, and CI (`mise tasks` lists all tasks).

| Command                                        | Purpose                                                                                                    |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `mise run all`                                 | Format, static checks, CSS build, pytest, OCI build/scan/smoke, Chromium install, browser journeys         |
| `mise run check`                               | Offline `check:local` (pre-commit) and network `check:network` (`uv`/npm/Trivy scans + OpenTofu, pre-push) |
| `mise run test`                                | Offline pytest (`≥91%` branch coverage, warnings as errors)                                                |
| `mise run test:browser` / `test:browser:cross` | Chromium journeys (`:8096`), or Firefox/WebKit smoke (`:8097`, `install:browser:cross`)                    |
| `mise run test:lighthouse:local`               | Temporary server (`:8098`) and strict 16-audit desktop/mobile Lighthouse matrix (`tmp/lighthouse/`)        |
| `mise run check:tofu`                          | Credential-free OpenTofu validation, `tflint`, and mocked plan tests                                       |
| `mise run check:links`                         | Network link check across content, portfolio, and `.agents/skills`                                         |
| `mise run check:image` / `test:image [digest]` | Build and Trivy-scan `tmp/www-image.tar`, then smoke-test the archive or remote digest                     |
| `mise run deploy <digest-ref> <commit-sha>`    | Manual Cloud Run rollout or rollback of a qualified Artifact Registry digest                               |

Set `BROWSER_BASE_URL=https://www.fmind.dev` to run browser suites against production. To audit an existing origin directly, run `mise run test:lighthouse -- --base-url <origin>`: all 16 desktop/mobile audits across sitemap-listed pages must score `1` in every category (performance-only misses retry twice and pass on a median of `1`). Dispatch [`quality.yml`](.github/workflows/quality.yml) (`gh workflow run quality.yml -f target=production`) to run cross-browser and Lighthouse suites on clean GitHub runners.

## Deployment

Cloud Run serves <https://www.fmind.dev/> in `www-fmind-dev` (`europe-west1`) with scale-to-zero (`min_instance_count = 0` on service and revision, max `5`, request-based CPU, `1` CPU, `512 MiB`, concurrency `32`, `30s` timeout). [`infra/`](infra/) and the [infra skill](.agents/skills/infra/SKILL.md) manage Cloud Run, Artifact Registry, keyless Workload Identity Federation, alerts, and remote state (`gs://www-fmind-dev-tfstate/infra/state`); OpenTofu ignores the image and CI-managed traffic.

Pushing to `main` runs `mise run all`, verifies the commit remains `main` HEAD before image build and before rollout, builds and pushes a non-root image with SBOM/provenance, and runs `mise run deploy <digest-ref> <commit-sha>` to scan and smoke-test the digest, verify a no-traffic candidate revision, route 100% of traffic, clean candidate tags, and run `test:deployed`:

```bash
mise run deploy europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev@sha256:<64-lowercase-hex> <40-lowercase-hex-commit>
```

Authenticate Docker to Artifact Registry before manual `deploy`. Neither CI nor `deploy` auto-rolls back after promotion: redeploy the preceding qualified digest to roll back, and inspect error logs with the owner identity. See the [release skill](.agents/skills/release/SKILL.md) for semver releases and MCP Registry publication (`server.json`), and [SECURITY.md](SECURITY.md) for vulnerability policy and advisory triage.

## Analytics and privacy

[`/privacy`](https://www.fmind.dev/privacy) documents the site's data practices:

- **First-party analytics**: cookieless HTML GET events in BigQuery (180-day partition expiry; no geography, IPs, raw user agents, full referrers, cookies, sessions, or traces). Query via [website-analytics](.agents/skills/website-analytics/SKILL.md) (`uv run --locked python -m scripts.website_analytics`).
- **Consented GA4**: `G-Z28QKD99V2` (property `538730900`) loads only on `www.fmind.dev` after explicit consent; footer **Cookie settings** revokes consent and clears `_ga` cookies.
- **Operational logs and tracing**: private Cloud Run logs expire after 30 days; `OTEL_EXPORTER_OTLP_*` enables tracing and `GOOGLE_CLOUD_PROJECT` adds Cloud Logging trace correlation.
- **FinOps**: use [finops-analytics](.agents/skills/finops-analytics/SKILL.md) for cost and budget reviews (`TF_VAR_billing_account` is required for OpenTofu plans and never committed).

## License

Application source code, infrastructure configuration, and build scripts are licensed under the [MIT License](LICENSE).

All rights are reserved on authored articles, curated news editions, and article media (`content/` and `static/img/articles/`), and on personal photographs and Fmind brand assets (`static/portrait.jpg`, `static/logo.png`, `static/img/avatar*.webp`, `static/img/logo.webp`, `static/img/og-image.jpg`, and `static/img/favicons/`): they are not licensed under MIT and may not be republished or redistributed without written permission. Company and certification logos under `static/img/companies/` and `static/img/certifications/` remain the property of their respective owners and are excluded from the MIT License.
