# www

<!-- mcp-name: dev.fmind/portfolio -->

The portfolio website of Médéric Hurier (Fmind). Built with **Go** + **[Templ](https://templ.guide)** (fully server-rendered), styled with **Tailwind CSS v4** + **DaisyUI v5**, and enhanced by a small vanilla JavaScript theme/menu and calculator controller. It ships as one self-contained binary with embedded assets: no client framework, Node.js project, database, cookies, or analytics tracker.

## Highlights

- **Server-rendered** with [Templ](https://templ.guide); the whole page and its assets ship inside one Go binary (`//go:embed`).
- **Fast**: inlined critical CSS, zstd/gzip text compression, pass-through delivery for precompressed assets, content-hashed immutable caching, self-hosted subset fonts, and `content-visibility` for below-the-fold sections.
- **Hardened**: a strict, per-request-nonce CSP (no `unsafe-inline`/`unsafe-eval` for scripts), the full suite of security headers, MCP cross-origin protection, and a request-body cap on the public `/mcp` endpoint.
- **Article-native**: articles rendered from validated embedded Markdown, with self-hosted responsive media, server-side syntax highlighting (Chroma, no client script), full-text search and color-coded tag filtering at `/articles/`, per-article social/JSON-LD metadata, related-article suggestions, a trimmed Atom feed, a raw Markdown source at `/articles/<slug>.md`, and a canonical-only sitemap.
- **Sites**: source-backed, server-rendered calculators under `/sites/`, with shareable GET assumptions, interactive cost figures, explicit cost boundaries, and no duplicated client formulas. Scenario updates preserve your place in the page. The LLM hosting tool compares demand, batch/cache API pricing, capacity, recorded latency, and cost per accepted task.
- **Agent-ready**: a closed-world, read-only [Model Context Protocol](https://modelcontextprotocol.io) server at `/mcp` (Streamable HTTP), tools + resources + prompts, server-card discovery, a canonical JSON snapshot at `/api/profile`, generated `/llms.txt` and `/llms-full.txt` surfaces, and connected `ProfilePage`/`Person`/`WebSite`/`BlogPosting` JSON-LD graphs.
- **Privacy-first**: no cookies, visitor identifiers, third-party scripts, runtime CDN dependencies, or client-side analytics. One aggregate structured record per HTML response can be routed from Cloud Logging to a 180-day partitioned BigQuery dataset; it retains no IP address, user-agent string, full referrer, session, or trace identifier.
- **Observability**: OpenTelemetry tracing (opt-in via `OTEL_EXPORTER_OTLP_ENDPOINT`) with `trace_id`/`span_id` correlated into structured logs.

## Prerequisites

- **Go** 1.26.6
- **[mise](https://mise.jdx.dev)** — manages the pinned toolchain (Go, golangci-lint, gotestsum, dprint, gitleaks, hadolint, lychee, typos, lefthook, trivy, actionlint, zizmor, OpenTofu, tflint, and the DaisyUI-bundled Tailwind CLI) and the task vocabulary.

## Local Development

```bash
mise install        # install the pinned toolchain
mise run install    # generate templates, tidy modules, and download dependencies
mise run watch      # compile Tailwind + templates and run the live-reload server
```

The site is served at `http://localhost:8080`. Configuration is environment-driven (see `.env.example`); with no environment set it runs in `development` mode on port 8080.

If port 8080 is already occupied, run `PORT=8081 mise run watch` and open `http://localhost:8081`.

## Articles

Articles live in `content/articles/<slug>.md` and their images in `static/img/articles/<slug>/`. Each Markdown file starts with strict TOML frontmatter containing `title`, `description`, `date`, `tags`, `slug`, optional `updated`, external `canonical`, and `syndicated`, and `draft`; unknown keys, unknown tags, invalid dates, or missing cover images fail startup. This site is canonical for everything it publishes, so archive entries omit `canonical` and record Medium or other copies as `syndicated` provenance. Production excludes drafts from pages and every discovery surface, while development renders drafts with `noindex` for review.

Tags come from a **closed vocabulary** declared in `templates/tags.go` — `Agent`, `Coding`, `LLM`, `RAG`, `MLOps`, `Cloud`, `Python`, `Project`, `Demo`, `Guide` — each with its own color, defined once as a `[data-tag='…']` rule in `assets/css/input.css`. Declaration order is display order. Adding a tag means one entry plus one color rule; anything outside the list — or a vocabulary entry that tags no article — fails startup rather than quietly adding an uncolored or empty filter chip.

Rendering normalizes what imported sources leave inconsistent: body headings are shifted so the shallowest becomes `<h2>` under the page title, and every body image gets intrinsic dimensions and asynchronous decoding. The first body image is preloaded as the LCP element; later figures load lazily. Article pages close with an author card, a booking call to action, and three tag-matched suggestions.

An image alone in its paragraph is an illustration, so it renders as a `<figure>` that **breaks out of the 896px text column** to the article's full padded width (up to 1280px) and links to its full resolution — a measure tuned for sentences paints a wide diagram's labels a few pixels tall. The following paragraph is folded in as a `<figcaption>` when its text repeats the image's alt. Every figure fits that width; nothing pans horizontally, so an illustration too wide to read when fitted is a diagram laid out wrong at its source and is fixed there. `figureSizes` in `articles.go` and the `.article-page` rules in `assets/css/input.css` describe one layout and must change together.

Sources are bounded by a **~2.4MP pixel budget** rather than a fixed width, and each ships the responsive rungs it is wide enough to earn (`<stem>-800.webp`, `<stem>-1280.webp`), so a phone never transfers a full-resolution diagram. The committed derivatives come from `mise run build:images` (`FORCE=1` rebuilds all) through the pinned pure-Go WebP encoder, so no image-processing binary is required. A missing rung fails the test suite; a missing cover derivative fails startup.

The parsed article set is the single source for the home page, `/articles/` (including its search index and `/articles/<slug>.md` sources), `/articles/feed.xml`, `/sitemap.xml`, `/llms.txt`, `/api/profile`, and MCP `list_publications`. New private drafts are promoted here by `pub export` from a private publications repository; once the live URL is recorded there, the private draft is removed and this repository owns the only published body.

## Decision Tools

Focused tools live under `/sites/` and are registered once in `templates.SITE_PAGES`. The registry drives their metadata and discovery surfaces. Calculations and input validation stay in Go; Templ owns presentation; native GET forms keep scenarios linkable. Follow the repository's [`site-page` skill](.agents/skills/site-page/SKILL.md) when adding or revising one.

The first tool, `/sites/llm-self-hosting/`, compares the current top ten open-weight models from Artificial Analysis with editable GKE accelerator, memory, utilization, staffing, and managed-API assumptions. It is a planning calculator: model ranks and list prices carry a visible snapshot date, and throughput remains a workload-specific input that must come from a pilot.

## Tasks

All tasks are defined in `mise.toml` and reused by the git hooks and CI:

| Task                    | Description                                                                             |
| ----------------------- | --------------------------------------------------------------------------------------- |
| `mise run install`      | Generate templates, tidy Go modules, and download dependencies                          |
| `mise run watch`        | Live-reload dev server (Go + Tailwind)                                                  |
| `mise run format`       | Format Go, Templ, and config/markup (goimports, gofumpt, templ, dprint)                 |
| `mise run check`        | Lint, vulnerability/secret/misconfig scans, format checks, and workflow audits          |
| `mise run check:typos`  | Check article prose against the spelling floor (typos)                                  |
| `mise run check:links`  | Check external content links are reachable (lychee; runs weekly in CI)                  |
| `mise run check:tofu`   | Validate and lint the OpenTofu module (runs in CI on `infra/` changes)                  |
| `mise run test`         | Run the test suite with coverage (gotestsum)                                            |
| `mise run test:browser` | Run Chromium journeys for both viewports, all public pages, and progressive enhancement |
| `mise run build`        | Generate templates, compile CSS, and build the binary                                   |
| `mise run build:images` | Regenerate deterministic downscaled article image derivatives (pure Go/WebP)            |
| `mise run build:image`  | Build the production OCI image locally                                                  |
| `mise run deploy <ref>` | Roll the Cloud Run service to a specific image digest (manual, mutates prod)            |

Browser tooling is pinned through mise, separate from the Go application. `mise run install` downloads the matching Chromium build. To repeat the browser suite against production, run `BROWSER_BASE_URL=https://www.fmind.dev mise run test:browser`. Reports and failure traces stay under `tmp/`. The vulnerability checks may refresh public databases and need network access; cloud credentials are not required.

## Deployment (Cloud Run)

The site runs on **Google Cloud Run** (project `www-fmind-dev`, `europe-west1`) and is served at <https://www.fmind.dev/> through a Cloud Run domain mapping. The repository and local binary are named `www`; the existing GCP project, service, state bucket, and service-account identifiers retain `www-fmind-dev` to avoid an unrelated production migration. All cloud resources are declared in [infra/](infra/) (OpenTofu): the Cloud Run service, Artifact Registry, keyless GitHub Actions CI (Workload Identity Federation), error alerting, and privacy-preserving analytics routing.

1. **Continuous delivery** — pull requests and pushes run [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml): `mise run all` formats, checks, tests, and builds the project, then runs the Chromium browser regressions and verifies the generated tree is clean. A `main` push builds the hardened distroless image with provenance and an SBOM, pushes it to Artifact Registry, and deploys its immutable digest. Authentication is keyless via branch-restricted WIF — no service-account keys.
1. **Infrastructure** — from [infra/](infra/): `tofu init && tofu apply`. OpenTofu owns the service shape (CPU/memory, scaling, env, probes, IAM); the image tag is rolled by CI (`lifecycle.ignore_changes`). Infrastructure changes are applied manually; CI validates them without applying them.
1. **Runtime config** — `ENVIRONMENT=production` is injected as a Cloud Run env var (see `infra/cloud_run.tf`); `PORT` is supplied by Cloud Run and tracing remains opt-in through standard `OTEL_EXPORTER_OTLP_*` variables.
1. **Local container** — `mise run build:image` builds the production image; run it with `docker run -p 8080:8080 www:local`.
1. **Manual rollout or rollback** — `mise run deploy <image-ref>` points the service at a specific image digest. On demand only; it never runs from a hook or from `mise run all`, and it sets only the image so OpenTofu keeps owning the rest of the service shape.

### Analytics

Every HTML response emits one aggregate structured record — path, status, referrer host, UTM dimensions, country, and a bot flag — which a Cloud Logging sink routes to a BigQuery dataset partitioned daily with a 180-day expiry (`infra/analytics.tf`). Nothing identifies a visitor: no cookie, IP address, user-agent string, full referrer, session, or trace identifier is retained. No BI layer is connected on purpose; the operator queries the table directly, and the query recipes live in the [`infra` skill](.agents/skills/infra/SKILL.md).

## Connecting an AI agent to `/mcp`

Once deployed, add `https://www.fmind.dev/mcp` as a custom MCP connector in Claude (Settings → Connectors) or ChatGPT (Developer mode). The server exposes closed-world, read-only tools — `get_profile`, `list_experience`, `list_certifications`, `list_publications`, `search_articles`, `list_projects`, `get_services` — a `portfolio://profile.json` resource, and the `assess_fit` and `brief_me` prompts. Server-card metadata is available at `/mcp/server-card` and the well-known compatibility route. Non-browser clients need no authentication; browser-originated calls are accepted only from the same origin.

The checked-in `server.json` is ready for the official MCP Registry. After the owner completes domain authentication, the one manual publication command is:

```bash
mcp-publisher publish
```
