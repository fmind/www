# www

Personal website and portfolio of [Médéric Hurier (Fmind)](https://www.fmind.dev/), freelance AI Architect specializing in AI agents, MLOps, and security. Built with Python 3.14, Litestar, strict Jinja, Tailwind CSS v4, DaisyUI v5, and Granian, with no client framework, database, or runtime CDN.

Alongside articles, [daily tech news](https://www.fmind.dev/news/), and read-only [agent and MCP endpoints](https://www.fmind.dev/agents) (`/mcp`, `/api/profile`, `/api/news`, `/llms.txt`, `/llms-full.txt`), the site hosts two decision tools with native GET forms and MCP tools:

- [LLM hosting budget tool](https://www.fmind.dev/sites/llm-self-hosting/) ([sources](src/www/sites/sources.md)): compares open-weight models on GKE (GPU and Cloud TPU) with managed APIs.
- [MCP context-cost calculator](https://www.fmind.dev/sites/mcp-context-cost/) ([sources](src/www/sites/mcp_context_cost/sources.md)): estimates token and input-cost overhead from measured MCP servers (GitHub default toolset, Filesystem, Memory, Playwright).

## Development

Requires [mise](https://mise.jdx.dev/) and Docker Engine with Buildx (no cloud credentials). `mise.toml`, `mise.lock`, and `.mise/locks/` pin the toolchain and transitive npm dependencies.

```bash
mise install
mise run install
mise run watch
```

Open `http://localhost:8080` (`PORT=8081` changes the port; `GRANIAN_HOST=0.0.0.0` opts in to LAN access). `uv run --locked www` starts the production entrypoint (`HOST=127.0.0.1` by default, `0.0.0.0` in the container image). See [`.env.example`](.env.example) for runtime variables (`.env` is not loaded automatically) and [AGENTS.md](AGENTS.md) for architecture, design rules, and `.agents/skills/` workflows.

## Tasks

`mise.toml` defines the task contract for local work, hooks, and CI; run `mise tasks` for the full list.

| Command                                        | Purpose                                                                                                                 |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `mise run all`                                 | Format, static checks, CSS build, pytest, OCI build/scan/smoke, Chromium install, browser journeys                      |
| `mise run check`                               | Offline `check:local` (pre-commit) and network `check:network` (`uv`/npm/Trivy scans and OpenTofu validation, pre-push) |
| `mise run test`                                | Offline pytest (`≥91%` branch coverage, warnings as errors)                                                             |
| `mise run test:browser` / `test:browser:cross` | Chromium journeys, or Firefox/WebKit smoke tests (`install:browser:cross` or `PW_TEST_CONNECT_WS_ENDPOINT`)             |
| `mise run test:lighthouse:local`               | Temporary server and strict 16-audit desktop/mobile Lighthouse matrix (`tmp/lighthouse/`)                               |
| `mise run check:tofu`                          | Credential-free OpenTofu validation, tflint, and mocked plan tests (`check:format` owns formatting)                     |
| `mise run check:links`                         | Network link check across content, portfolio, and `.agents/skills`                                                      |
| `mise run check:image` / `test:image [digest]` | Build and Trivy-scan `tmp/www-image.tar`, then smoke-test the archive or remote digest                                  |
| `mise run deploy <digest-ref> <commit-sha>`    | Manual Cloud Run rollout or rollback of a qualified Artifact Registry digest                                            |

Browser suites share local port `8096` and must run sequentially; set `BROWSER_BASE_URL=https://www.fmind.dev` to target production. For Lighthouse against an existing origin, run `mise run test:lighthouse -- --base-url <origin>`: all 16 desktop/mobile audits across sitemap-listed pages must score `1` in every category (if only performance misses, it retries twice and passes on a median of `1`). Dispatch [`quality.yml`](.github/workflows/quality.yml) (`gh workflow run quality.yml -f target=production`) to run the cross-browser and Lighthouse suites on clean GitHub runners.

## Deployment

Cloud Run serves <https://www.fmind.dev/> in project `www-fmind-dev` (`europe-west1`) with scale-to-zero (`min_instance_count = 0` on service and revision, max `5`, request-based CPU, `1` CPU, `512 MiB`, concurrency `32`, `30s` timeout). [`infra/`](infra/) and the [infra skill](.agents/skills/infra/SKILL.md) manage Cloud Run settings, Artifact Registry, keyless Workload Identity Federation, monitoring alerts, and remote state (`gs://www-fmind-dev-tfstate/infra/state`); OpenTofu ignores the image and CI-managed traffic.

A push to `main` runs `mise run all`, confirms the commit is still `main` HEAD (the deploy job checks again before the image build and before the rollout, so a re-run cannot ship an older commit over a newer one), builds and pushes a non-root image with SBOM/provenance, and runs `mise run deploy <digest-ref> <commit-sha>` to scan and smoke-test the immutable digest, verify a no-traffic candidate revision, route 100% of traffic to that revision, remove candidate tags, and run `test:deployed`:

```bash
mise run deploy europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev@sha256:<64-lowercase-hex> <40-lowercase-hex-commit>
```

Authenticate Docker to Artifact Registry before a manual `deploy`. Neither CI nor `deploy` rolls back automatically after promotion: redeploy the preceding qualified digest to roll back, and review error logs separately with the owner identity. Follow the [release skill](.agents/skills/release/SKILL.md) for semver releases and MCP Registry publication (`server.json`), and [SECURITY.md](SECURITY.md) for vulnerability policy and advisory review.

## Analytics and privacy

[`/privacy`](https://www.fmind.dev/privacy) describes the site's data practices:

- **First-party analytics**: cookieless HTML GET events exported to BigQuery (180-day partition expiry, empty geography, no IPs, raw user agents, full referrers, cookies, sessions, or traces). Query with the [website-analytics skill](.agents/skills/website-analytics/SKILL.md) (`uv run --locked python -m scripts.website_analytics`).
- **Consented GA4**: `G-Z28QKD99V2` (property `538730900`) loads only on `www.fmind.dev` after explicit consent; **Cookie settings** in the footer revokes consent and deletes `_ga` cookies.
- **Operational logs and tracing**: private Cloud Run logs expire after 30 days. Opt-in tracing uses `OTEL_EXPORTER_OTLP_*`, and `GOOGLE_CLOUD_PROJECT` adds Cloud Logging trace correlation.
- **FinOps**: use the [finops-analytics skill](.agents/skills/finops-analytics/SKILL.md) for cost and budget reviews (`TF_VAR_billing_account` is required for OpenTofu plans and never committed).

## License

Application source code, infrastructure configuration, and build scripts are licensed under the [MIT License](LICENSE).

All rights are reserved on authored articles, curated news editions, and article media (`content/` and `static/img/articles/`), and on personal photographs and Fmind brand assets (`static/portrait.jpg`, `static/logo.png`, `static/img/avatar*.webp`, `static/img/logo.webp`, `static/img/og-image.jpg`, and `static/img/favicons/`): they are not licensed under MIT and may not be republished or redistributed without written permission. Company and certification logos under `static/img/companies/` and `static/img/certifications/` remain the property of their respective owners and are excluded from the MIT License.
