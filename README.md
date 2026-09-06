# www

<!-- mcp-name: dev.fmind/portfolio -->

The portfolio website of Médéric Hurier (Fmind). It is a fully server-rendered Python application built with [Litestar](https://litestar.dev/), [Jinja](https://jinja.palletsprojects.com/), Tailwind CSS v4, and DaisyUI v5. A small vanilla JavaScript theme, menu, and calculator controller provide progressive enhancement. There is no client framework, Node.js application project, database, cookie, or analytics tracker.

## Highlights

- **Server-rendered** by Litestar and strict, autoescaped Jinja templates packaged under `src/www/templates/`; Granian serves the ASGI application.
- **Fast**: inlined critical CSS, Brotli/gzip page compression, content-hashed immutable static caching, self-hosted subset fonts, and `content-visibility` for below-the-fold sections. Static files keep their on-disk bytes so strong ETags, byte ranges, and HEAD responses agree.
- **Hardened**: a strict, per-request-nonce CSP with no `unsafe-inline` or `unsafe-eval` scripts, the full security-header suite, MCP cross-origin protection, and a request-body cap on the public `/mcp` endpoint.
- **Article-native**: strictly validated Markdown, responsive self-hosted media, server-side Pygments highlighting, full-text search and tag filtering at `/articles/`, social and JSON-LD metadata, related articles, Atom, raw Markdown at `/articles/<slug>.md`, and a canonical-only sitemap.
- **Sites**: source-backed calculators under `/sites/` use shareable GET assumptions, server-owned formulas, explicit cost boundaries, and progressive enhancement. The LLM hosting tool compares demand, batch/cache API pricing, capacity, measured latency, and cost per accepted task.
- **Agent-ready**: a closed-world, read-only [Model Context Protocol](https://modelcontextprotocol.io) server at `/mcp` with tools, resources, prompts, server-card discovery, `/api/profile`, `/llms.txt`, `/llms-full.txt`, and connected JSON-LD graphs.
- **Privacy-first**: no cookies, visitor identifiers, third-party scripts, runtime CDN dependencies, or client-side analytics. One aggregate record per HTML response can be routed from Cloud Logging to a 180-day partitioned BigQuery dataset without retaining an IP address, user-agent string, full referrer, session, or trace identifier.
- **Observable**: optional OpenTelemetry export through `OTEL_EXPORTER_OTLP_ENDPOINT`, with `trace_id` and `span_id` correlation in structured logs.

## Prerequisites

- Python 3.14 (mise and the production image pin 3.14.7)
- [mise](https://mise.jdx.dev/) for the pinned Python, `uv`, browser, infrastructure, security, and formatting toolchain
- Docker Engine with the Buildx plugin for the production image gate in `mise run all`

A fresh checkout needs network access for `mise install`. The first `mise run all` also installs Chromium, pulls the production base image, and refreshes vulnerability databases. Warm application tests remain local and need no cloud credentials.

## Local Development

```bash
mise install        # install the pinned toolchain
mise run install    # sync the locked development environment and install Chromium
mise run watch      # run Granian with reload alongside the Tailwind watcher
```

The site is served at `http://localhost:8080`. Configuration is environment-driven through `.env.example`; with no environment set, it runs in `development` mode on port 8080. Use `PORT=8081 mise run watch` when the default port is occupied.

`src/www/app.py` is the composition root and exports `www.app:app`. `src/www/__main__.py` validates runtime configuration and starts Granian. Jinja templates are package data, while `content/` and `static/` remain explicit deploy-time trees. The production image copies both beside the locked virtual environment under `/app`.

## Articles

Articles live in `content/articles/<slug>.md`, with images under `static/img/articles/<slug>/`. Each source begins with strict TOML frontmatter containing `title`, `description`, `date`, `tags`, `slug`, optional `updated`, external `canonical`, and `syndicated`, plus `draft`. Unknown keys or tags, invalid dates, duplicate slugs, and missing cover assets fail application construction. Production excludes drafts from pages and every discovery surface; development renders them with `noindex` for review.

Tags use the closed vocabulary in `src/www/tags.py`: `Agent`, `Coding`, `LLM`, `RAG`, `MLOps`, `Cloud`, `Python`, `Project`, `Demo`, and `Guide`. Each needs a matching `[data-tag='…']` rule in `assets/css/input.css` and must tag at least one article. Declaration order is display order.

`src/www/content.py` parses and normalizes Markdown with markdown-it-py, shifts body headings beneath the page title, enhances body images, and folds a repeated image-alt paragraph into a caption. Pygments highlighting is centralized in `src/www/highlighting.py`. The first body image is preloaded; later figures load lazily. Standalone illustrations break out of the 896px text column up to the 1280px figure width, link to their full-resolution source, and never pan horizontally.

Sources are bounded by a roughly 2.4MP pixel budget. Each image ships only the responsive rungs it can support (`<stem>-800.webp` and `<stem>-1280.webp`). Generate and commit them with `mise run build:images`; the provenance lock binds exact source and target SHA-256 digests to the pinned Pillow/WebP encoder recipe, then rebuilds only changed, missing, tampered, or recipe-stale rungs. The canonical `check` runs `check:images`, which validates the complete archive without writing.

The validated article collection is the sole source for HTML, search, raw Markdown, Atom, sitemap, LLM text, JSON, and MCP publication surfaces. Markdown responses make rendered root-relative links absolute while preserving code examples and external URLs. Article changes follow the authorized [article publication workflow](.agents/skills/article/SKILL.md); this repository owns the published body.

## Decision Tools

Focused tools live under `/sites/`. `src/www/data.py:SITE_PAGES` drives metadata, the sitemap, LLM text, JSON, MCP discovery, and article relationships; `src/www/app.py` wires each page's route, template, and view builder explicitly. Calculation models and validation live under `src/www/sites/`; Jinja owns presentation; native GET forms keep scenarios linkable. Follow the repository's [`site` skill](.agents/skills/site/SKILL.md) when adding or revising one.

The first tool, `/sites/llm-self-hosting/`, compares the current top ten open-weight models from Artificial Analysis with editable GKE accelerator, memory, utilization, staffing, and managed-API assumptions. It is a planning calculator: ranks and list prices carry a visible snapshot date, and throughput remains a workload-specific input that must come from a pilot.

## Tasks

All tasks are defined in `mise.toml` and reused by Lefthook and CI:

| Task                                                                   | Description                                                                           |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `mise run install`                                                     | Frozen `uv` sync, Lefthook installation, and pinned Chromium installation             |
| `mise run watch`                                                       | Granian ASGI reload server and Tailwind watcher                                       |
| `mise run format`                                                      | Ruff Python imports/formatting, dprint, and OpenTofu formatting                       |
| `mise run check`                                                       | Ruff, ty, metadata/lock, dependency, Dockerfile/IaC, and workflow checks              |
| `mise run check:image`                                                 | Build and scan the exact production OCI archive (Docker with Buildx required)         |
| `mise run check:images`                                                | Validate all image derivatives, hashes, modes, dimensions, and recipe without writing |
| `mise run check:typos`                                                 | Check article prose against the spelling floor                                        |
| `mise run check:links`                                                 | Check external content links (network-dependent; scheduled weekly in CI)              |
| `mise run check:tofu`                                                  | Validate and lint OpenTofu (network-dependent; runs in CI on `infra/` changes)        |
| `mise run test`                                                        | Run pytest offline with branch coverage of at least 85%                               |
| `mise run test:browser`                                                | Run Chromium journeys on desktop/light and mobile/dark                                |
| `mise run test:image`                                                  | Smoke-test the already-built production OCI archive through Docker                    |
| `mise run test:lighthouse -- --base-url <origin> [--mode full\|smoke]` | Run the strict five-category Lighthouse matrix; never in `all`                        |
| `mise run coverage`                                                    | Show the terminal coverage report                                                     |
| `mise run build`                                                       | Compile Tailwind CSS and build clean wheel and source distributions                   |
| `mise run build:images`                                                | Reconcile changed, missing, tampered, or recipe-stale Pillow derivatives              |
| `mise run build:image`                                                 | Build the production OCI image archive at `tmp/www-image.tar`                         |
| `mise run deploy <digest-ref>`                                         | Roll Cloud Run to one repository-pinned image digest (manual and production-mutating) |

`mise run all` runs sequentially: format, static checks, the package/CSS build, pytest, the exact OCI archive build and scan, its bounded runtime smoke test, one pinned Chromium installation, then browser journeys. The image smoke reuses the archive produced by `check:image`; it never builds. The final browser task skips its automatic prerequisites because `all` has already built and installed them once; standalone `test:browser` keeps its normal dependencies. Docker Engine with Buildx must be running, and a cold run needs network access as described above.

Lighthouse remains an explicit, non-default audit because it needs a target origin and runs 174 audits in full mode. Install Chromium first with `mise run install:browser`; if it is absent, the harness reports the equivalent `playwright install chromium` remediation. Use `mise run test:lighthouse -- --base-url http://127.0.0.1:8080 --mode smoke` for the four-audit local smoke matrix, or omit `--mode smoke` for full qualification. To exercise the browser suite against production, use `BROWSER_BASE_URL=https://www.fmind.dev mise run test:browser`. Reports and traces stay under `tmp/`. Local application checks need no cloud credentials.

## Deployment

The site runs on Google Cloud Run in project `www-fmind-dev`, region `europe-west1`, and is served at <https://www.fmind.dev/>. Existing GCP identifiers retain `www-fmind-dev` to avoid an unrelated production migration. OpenTofu under [infra/](infra/) owns the Cloud Run shape, Artifact Registry, keyless GitHub Actions identity, alerts, and privacy-preserving analytics route.

1. **Continuous delivery** — pull requests and pushes run [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml). Actions use immutable commit pins, updated through Dependabot. A `main` push builds the non-root OCI image with provenance and an SBOM, pushes it to Artifact Registry, scans and smoke-tests that exact digest, then deploys it through branch-restricted Workload Identity Federation.
1. **Infrastructure** — `tofu -chdir=infra init && tofu -chdir=infra apply` is always manual. OpenTofu owns CPU, memory, scaling, environment, probes, and IAM; CI owns only the image digest through `lifecycle.ignore_changes`.
1. **Runtime** — Cloud Run injects `PORT`, OpenTofu sets `ENVIRONMENT=production`, and standard `OTEL_EXPORTER_OTLP_*` variables enable tracing. The container runs as UID/GID 10001 with a locked virtual environment, `content/`, and `static/` under `/app`.
1. **Local image** — run `mise run build:image`, load the archive with `docker load --input tmp/www-image.tar`, then run `docker run -p 8080:8080 www:local`.
1. **Manual rollout or rollback** — `mise run deploy europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev@sha256:<64-lowercase-hex>` accepts exactly one digest from the production repository and changes only the service image. Tags, foreign repositories, and extra flags fail before `gcloud`; the task never runs from a hook or `mise run all`.

Reconcile reviewed `infra/` changes before rolling out an application image. The Python runtime is qualified for the declared concurrency of **8**, a **512 MiB** service limit, and the startup probe's **6 attempts at 5-second intervals**. CI and the manual deploy task change only the image; merging a branch does not apply service settings. After each image rollout, verify health, traffic, error logs, and browser journeys; keep the previous known-good digest available for rollback.

### Analytics

Each HTML response emits one aggregate structured record: path, status, referrer host, UTM dimensions, and a bot flag. The schema keeps `country` empty because the public Cloud Run origin has no trusted geography header. A Cloud Logging sink routes records to a BigQuery dataset partitioned daily with a 180-day expiry. No cookie, IP address, user-agent string, full referrer, session, trace identifier, or derived location is retained. Query recipes live in the [`infra` skill](.agents/skills/infra/SKILL.md).

## Connecting an AI Agent to `/mcp`

After deployment, add `https://www.fmind.dev/mcp` as a custom MCP connector. The server exposes the closed-world, read-only tools `get_profile`, `list_experience`, `list_certifications`, `list_publications`, `search_articles`, `list_projects`, and `get_services`; the `portfolio://profile.json` resource; and the `assess_fit` and `brief_me` prompts. Server-card metadata is available at `/mcp/server-card` and the well-known compatibility route. Browser calls are accepted only from the same origin; non-browser clients need no authentication.

The checked-in `server.json` is ready for the official MCP Registry. Publication remains one explicit owner action after domain authentication:

```bash
mcp-publisher publish
```
