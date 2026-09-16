# www

<!-- mcp-name: io.github.fmind/portfolio -->

The portfolio website of Médéric Hurier (Fmind). It is a fully server-rendered Python application built with [Litestar](https://litestar.dev/), [Jinja](https://jinja.palletsprojects.com/), Tailwind CSS v4, and DaisyUI v5. Small vanilla JavaScript section-menu and calculator controllers provide progressive enhancement only on the pages that use them. There is no client framework, Node.js application project, database, cookie, or analytics tracker.

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

`.env.example` documents the supported variables; the application does not automatically load a `.env` file. Export variables in your shell or provide them through your process manager.

The server reloads on changes under `src/`, `content/`, and `static/`, including templates and compiled CSS. Browser artifacts under `tmp/`, distribution builds, and test edits do not restart workers. Restart `mise run watch` after changing environment or project configuration.

`src/www/app.py` is the composition root and exports `www.app:app`. `src/www/__main__.py` validates runtime configuration and starts Granian. Jinja templates are package data, while `content/` and `static/` remain explicit deploy-time trees. The production image copies both beside the locked virtual environment under `/app`.

## Articles

Articles live in `content/articles/<slug>.md`, with images under `static/img/articles/<slug>/`. Each source begins with strict TOML frontmatter containing `title`, `description`, `date`, `tags`, `slug`, optional `updated`, external `canonical`, and `syndicated`, plus `draft`. Unknown keys or tags, invalid dates, duplicate slugs, and missing cover assets fail application construction. Production excludes drafts from pages and every discovery surface; development renders them with `noindex` for review.

Archive cards defer off-screen layout with native CSS `content-visibility`; their links remain available to keyboard navigation and require no JavaScript.

Tags use the closed vocabulary in `src/www/tags.py`: `Agent`, `Coding`, `LLM`, `RAG`, `MLOps`, `Cloud`, `Python`, `Project`, `Demo`, and `Guide`. Each needs a matching `[data-tag='…']` rule in `assets/css/input.css` and must tag at least one article. Declaration order is display order.

`src/www/content.py` parses and normalizes Markdown with markdown-it-py, shifts body headings beneath the page title, enhances body images, and folds a repeated image-alt paragraph into a caption. Pygments highlighting is centralized in `src/www/highlighting.py`. The first body image is preloaded; later figures load lazily. Standalone illustrations break out of the 896px text column up to the 1280px figure width, link to their full-resolution source, and never pan horizontally.

Sources are bounded by a roughly 2.4MP pixel budget. Each image ships only the responsive rungs it can support (`<stem>-800.webp` and `<stem>-1280.webp`). Generate and commit them with `mise run build:images`; the provenance lock binds exact source and target SHA-256 digests to the pinned Pillow/WebP encoder recipe, then rebuilds only changed, missing, tampered, or recipe-stale rungs. The canonical `check` runs `check:images`, which validates the complete archive without writing.

The validated article collection is the sole source for HTML, search, raw Markdown, Atom, sitemap, LLM text, JSON, and MCP publication surfaces. Markdown responses make rendered root-relative links absolute while preserving code examples and external URLs. Article changes follow the authorized [article publication workflow](.agents/skills/article/SKILL.md); this repository owns the published body.

## Branding

The light website palette follows [fmind/theme](https://github.com/fmind/theme): white canvas, light gray panels, charcoal text, and the logo blue `#174EA6` for links, controls, and focus. `assets/css/input.css` owns interface colors; `src/www/highlighting.py` maps the same syntax roles to the existing token classes (blue keywords/functions, green strings, orange literals, purple types, gray comments, and red errors). Update both from the theme’s `checks/palette.yaml` and `themes/ptpython/fmind.py`; the website builds independently of that checkout. Company accent borders preserve their respective brand colors as explicit exceptions; `tests/test_palette.py` rejects unreviewed colors elsewhere in authored interface CSS.

The full-resolution, losslessly optimized PNG masters are available at `https://www.fmind.dev/logo.png` and `https://www.fmind.dev/banner.png`. These stable URLs serve PNG bytes directly with cache revalidation and also retain the artwork's transparency for reuse.

Navigation uses a 96px lossless WebP logo for the 24–40px display, while favicons and home-screen icons use appropriately sized derivatives. Default social previews fit the complete banner onto a white 1200×630 progressive JPEG canvas; article previews retain their own covers. Regenerate these committed assets from `static/logo.png` and `static/banner.png` with `mise run build:branding`. Home-screen icons declare `any` because the logo's outer ring extends beyond the maskable safe area.

The top navigation keeps Portfolio, Articles, and Sites visible on every screen. The portfolio section rail appears from 1600px, where the content margin accommodates its 192px width without covering text; desktop widths from 1024px to 1599px use an “On this page” dropdown in a compact sticky row below the primary navigation. Mobile and tablet screens below 1024px hide section navigation to preserve reading space. The row reserves its own space, and section anchors clear both rows. Section links work without JavaScript; JavaScript adds the active-section indicator, closes the dropdown after selection, and supports Escape. Social profile icons stay in the header at every width. The header stays on one row, and the Fmind.dev wordmark appears when its column has enough room. Current consulting availability and the paid mentoring duration appear beside the homepage contact actions and derive from the same service data as the Services section.

The public `/portrait.jpg` download is a sanitized JPEG, separate from the small responsive avatars. Keep the original JPEG master outside `static/` and regenerate the download with `mise run build:portrait /path/to/private-master.jpg`. The exporter applies orientation, retains the ICC color profile, and discards EXIF, XMP, comments, and photographer contact records. It does not overwrite the master. The public download and `/static/portrait.jpg` are checked for metadata in the HTTP regression suite.

## Conference Contact Page

Share `https://www.fmind.dev/connect` at conferences. This visitor landing page offers LinkedIn, a downloadable contact card, and a link to the full website. `/connect.vcf` derives its public name, nickname, role, email, work city/country, languages, professional summary, expertise, leadership roles, active credentials, social profiles, booking link, and website from the portfolio data at application startup. It embeds a JPEG copy of the public portrait with image metadata removed. The card includes a stable public identifier and source URL; labeled links also appear in its notes for importers that display every URL as a generic website.

The export stays on [vCard 3.0](https://www.rfc-editor.org/rfc/rfc2426), with UTF-8 text, CRLF endings, and lines folded at 75 octets. It contains no telephone number, street address, birthday, or precise coordinates. Add only details intended for publication: the repository and the download are public. Visitors confirm saving the contact in their own app; some Android browsers require importing the downloaded `.vcf` from Contacts. Field display and duplicate-contact handling depend on the receiving app.

Open `https://www.fmind.dev/scan` to show someone the QR code. It encodes the permanent `/connect` URL, so existing printed codes still work and contact actions can change without replacing the code. The QR display includes a tappable destination and is excluded from search indexing and the sitemap; `/connect` remains discoverable. Both pages and the contact download work without JavaScript or third-party QR services.

Regenerate the displayed QR asset with the pinned [Segno CLI](https://segno.readthedocs.io/en/stable/command-line.html); it is a build-time tool, with no application dependency:

```bash
uvx --from segno==1.6.6 segno --error M --border 4 --scale 8 --light white --output static/img/connect-qr.svg https://www.fmind.dev/connect
```

## Decision Tools

Focused tools live under `/sites/`. `src/www/data.py:SITE_PAGES` drives metadata, the sitemap, LLM text, JSON, MCP discovery, and article relationships; `src/www/app.py` wires each page's route, template, and view builder explicitly. Calculation models and validation live under `src/www/sites/`; Jinja owns presentation; native GET forms keep scenarios linkable. Follow the repository's [`site` skill](.agents/skills/site/SKILL.md) when adding or revising one.

The first tool, `/sites/llm-self-hosting/`, compares the current top ten open-weight models from Artificial Analysis with editable GKE accelerator, memory, utilization, staffing, and managed-API assumptions. It includes L4 and RTX PRO 6000 nodes, separate on-demand and resource-CUD billing choices, and a compact hardware starting point based on memory fit and whole-machine cost. Commitments remain billed while idle. It is a planning calculator: ranks and list prices carry a visible snapshot date, and throughput remains a workload-specific input that must come from a pilot. The [source snapshot](src/www/sites/sources.md) records verified rates, scope, and recommendation rules.

## Tasks

All tasks are defined in `mise.toml` and reused by Lefthook and CI:

| Task                                                                              | Description                                                                           |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `mise run install`                                                                | Frozen `uv` sync, Lefthook installation, and pinned Chromium installation             |
| `mise run watch`                                                                  | Granian ASGI reload server and Tailwind watcher                                       |
| `mise run format`                                                                 | Ruff Python imports/formatting, dprint, and OpenTofu formatting                       |
| `mise run check`                                                                  | Ruff, ty, metadata/lock, dependency, Dockerfile/IaC, and workflow checks              |
| `mise run check:image`                                                            | Build and scan the exact production OCI archive (Docker with Buildx required)         |
| `mise run check:image:deployed`                                                   | Resolve and scan every serving Cloud Run revision with Trivy                          |
| `mise run check:images`                                                           | Validate all image derivatives, hashes, modes, dimensions, and recipe without writing |
| `mise run check:typos`                                                            | Check article prose against the spelling floor                                        |
| `mise run check:links`                                                            | Check external content links (network-dependent; scheduled weekly in CI)              |
| `mise run check:tofu`                                                             | Validate and lint OpenTofu (network-dependent; runs in CI on `infra/` changes)        |
| `mise run test`                                                                   | Run pytest offline with branch coverage of at least 85%                               |
| `mise run test:browser`                                                           | Run Chromium journeys on desktop and mobile in light mode                             |
| `mise run test:image`                                                             | Smoke-test the already-built production OCI archive through Docker                    |
| `mise run test:lighthouse -- --base-url <origin> [--mode full\|smoke\|portfolio]` | Run the strict five-category Lighthouse matrix; never in `all`                        |
| `mise run coverage`                                                               | Show the terminal coverage report                                                     |
| `mise run build`                                                                  | Compile Tailwind CSS and build clean wheel and source distributions                   |
| `mise run build:images`                                                           | Reconcile changed, missing, tampered, or recipe-stale Pillow derivatives              |
| `mise run build:image`                                                            | Build the production OCI image archive at `tmp/www-image.tar`                         |
| `mise run deploy <digest-ref>`                                                    | Roll Cloud Run to one repository-pinned image digest (manual and production-mutating) |

`mise run all` runs sequentially: format, static checks, the package/CSS build, pytest, the exact OCI archive build and scan, its bounded runtime smoke test, one pinned Chromium installation, then browser journeys. The sequential gate reuses its compiled CSS and package build through mise’s `--skip-deps` option; standalone test tasks still prepare their dependencies. The image smoke reuses the archive produced by `check:image`; it never builds. Docker Engine with Buildx must be running, and a cold run needs network access as described above.

Lighthouse remains an explicit, non-default audit. `mise run test:lighthouse:local` builds the candidate and uses Playwright to start and stop a temporary server for the ten-audit portfolio matrix. Set `BROWSER_BASE_URL` only when intentionally auditing another origin; the direct `test:lighthouse` task still requires a target origin. Full mode audits every sitemap page on desktop and mobile, then adds 48 stress audits; its count grows with the sitemap. Install Chromium first with `mise run install:browser`; if it is absent, the harness reports the equivalent `playwright install chromium` remediation. Use `mise run test:lighthouse -- --base-url http://127.0.0.1:8080 --mode smoke` for the four-audit local smoke matrix, use `--mode portfolio` for ten audits covering `/`, `/connect`, `/privacy`, `/articles/`, and `/sites/` without article or decision-page bodies, or omit `--mode` for full qualification. `--plan` validates tools without fetching the sitemap, so full-mode totals are unknown until execution. To exercise the browser suite against production, use `BROWSER_BASE_URL=https://www.fmind.dev mise run test:browser`. Local application checks need no cloud credentials.

The [weekly/manual browser qualification workflow](.github/workflows/quality.yml) runs the portfolio Lighthouse matrix and a small Firefox/WebKit suite in separate jobs, preserving reports for 14 days. It does not deploy. For native cross-browser checks, run `mise run install:browser:cross` and `mise run test:browser:cross`; Linux also needs Playwright’s documented system libraries. An administrator can provision these with `playwright install-deps firefox webkit`; browser downloads alone do not install them. The ephemeral CI runner installs them through `mise run install:browser:cross -- --with-deps`. Alternatively, point `PW_TEST_CONNECT_WS_ENDPOINT` at a matching-version [Playwright server in its official Docker image](https://playwright.dev/docs/docker#remote-connection); the task then uses the container’s browser libraries. Cross-browser checks stay separate from `all` because they require those additional platform dependencies. They cover desktop/mobile reflow, keyboard and no-JavaScript navigation, and real contact downloads; they do not establish parity with every shipping Safari version or replace screen-reader testing.

Configuration and working-tree secret scans exclude generated `tmp/`, `.venv/`, and `dist/` trees. Secret scans of Git history keep the default rules.

Asset maintenance also includes `mise run build:branding` for PNG-derived branding and `mise run build:fonts` for the pinned self-hosted font subsets. These generators and `build:portrait` run only on demand; image derivatives are validated by `all` without being regenerated. `watch` and `test:watch` are long-running development tasks, while `clean` deliberately removes generated files and should not be used as a verification task.

Font rebuilds preserve upstream timestamps so identical inputs produce identical asset hashes. All pages preload the body font; only article pages preload the code font. Other uses, such as the QR page's destination link, load the code font through CSS when needed.

Operational commands live in `scripts/deploy.py` and `scripts/image_smoke.py`, outside the shipped application package. The image smoke uses the MCP SDK with bounded loopback HTTP requests and checks image identity, non-root execution, file permissions, HTTP, tools, resources, and prompts. `mise` keeps their public task names stable. Browser tooling keeps its Node dependencies in mise installations; there is no repository Node application or runtime Plotly dependency.

## Deployment

The site runs on Google Cloud Run in project `www-fmind-dev`, region `europe-west1`, and is served at <https://www.fmind.dev/>. Existing GCP identifiers retain `www-fmind-dev` to avoid an unrelated production migration. OpenTofu under [infra/](infra/) owns the Cloud Run shape, Artifact Registry, keyless GitHub Actions identity, alerts, and privacy-preserving analytics route.

1. **Continuous delivery** — pull requests and pushes run [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml). Actions use immutable commit pins, updated through Dependabot. A `main` push builds the non-root OCI image with provenance and an SBOM, pushes it to Artifact Registry, scans and smoke-tests that exact digest, then deploys it through Workload Identity Federation restricted to `main` and the immutable GitHub repository and owner IDs.
1. **Infrastructure** — `tofu -chdir=infra init && tofu -chdir=infra apply` is always manual. OpenTofu owns CPU, memory, scaling, environment, probes, and IAM; CI owns only the image digest through `lifecycle.ignore_changes`.
1. **Runtime** — Cloud Run injects `PORT`, OpenTofu sets `ENVIRONMENT=production`, and standard `OTEL_EXPORTER_OTLP_*` variables enable tracing. The container runs as UID/GID 10001 with a locked virtual environment, `content/`, and `static/` under `/app`.
1. **Local image** — run `mise run build:image`, load the archive with `docker load --input tmp/www-image.tar`, then run `docker run -p 8080:8080 www:local`.
1. **Manual rollout or rollback** — `mise run deploy europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev@sha256:<64-lowercase-hex>` accepts exactly one digest from the production repository and changes only the service image. Tags, foreign repositories, and extra flags fail before `gcloud`; the task never runs from a hook or `mise run all`. Before a new rollout, qualify that exact digest with `mise run check:image:digest <digest-ref>` and `mise run test:image <digest-ref>`; rollback should select a previously qualified digest.

Reconcile reviewed `infra/` changes before rolling out an application image. The Python runtime is qualified for the declared concurrency of **8**, a **512 MiB** service limit, scale-to-zero with at most **5 instances**, and the startup probe's **6 attempts at 5-second intervals**. CI and the manual deploy task change only the image; merging a branch does not apply service settings. After each image rollout, verify health, traffic, error logs, and browser journeys; keep the previous known-good digest available for rollback.

The weekly [security workflow](.github/workflows/security.yml) scans full Git history and source, then uses a separate read-only cloud identity to resolve and scan every image receiving traffic. It retains fixed and unfixed HIGH/CRITICAL advisory reports for 30 days and enforces the same fixable finding gate as deployment. [SECURITY.md](SECURITY.md) records the review owner, residual exposure, and next review. GitHub secret scanning, push protection, dependency alerts, and Dependabot security updates are enabled; main rejects deletion and force pushes while allowing ordinary owner pushes.

### Analytics

Visitor-facing details are available at `/privacy`. Article headings include 🔗 section permalinks with stable existing fragment identifiers. Activating one copies the full section URL and announces success; if clipboard access fails, the anchor still works and the page explains how to copy the address manually. Pages do not advertise an installable app.

Each HTML response emits one aggregate structured record: path, status, referrer host, UTM dimensions, and a bot flag. The schema keeps `country` empty because the public Cloud Run origin has no trusted geography header. A Cloud Logging sink routes records to a BigQuery dataset partitioned daily with a 180-day expiry. These aggregate analytics records retain no cookie, IP address, user-agent string, full referrer, session, trace identifier, or derived location. Cloud Run separately writes private operational request logs, which can contain IP addresses, user agents, and complete request URLs; the Cloud Logging `_Default` bucket retains those logs for 30 days.

Use the repository [`website-analytics` skill](.agents/skills/website-analytics/SKILL.md) (`/website-analytics` or `$website-analytics`, depending on the agent) for a text report of usage, popular pages, referrals, campaigns, and trends. It uses the existing `gcloud` login and no-charge BigQuery table reads, with no Looker dependency. The helper `uv run --locked python -m scripts.website_analytics` emits aggregate JSON for the last seven complete days versus the preceding seven in `Europe/Paris`; use `--days 28`, `--end-date YYYY-MM-DD` (exclusive), or `--timezone` to override. Reads stop at 100,000 retained rows, 64 MiB, or 100 pages and reject incomplete or changing data. Reports count successful non-bot HTML responses, not unique visitors, sessions, or conversions. Keep production reports out of Git.

## Connecting an AI Agent to `/mcp`

After deployment, add `https://www.fmind.dev/mcp` as a custom MCP connector. The server exposes the closed-world, read-only tools `get_profile`, `list_experience`, `list_certifications`, `list_publications`, `search_articles`, `list_projects`, `get_services`, `get_article`, and `compare_llm_hosting`; the `portfolio://profile.json` resource; and the `assess_fit` and `brief_me` prompts. The JSON profile advertises `/api/profile/schema.json` through a `Link: rel="describedby"` header; its JSON Schema derives from the same public serialization model. Server-card metadata, including the resource URI and MIME type, is available at `/mcp/server-card` and the well-known compatibility route. Browser calls are accepted only from the same origin; non-browser clients need no authentication.

The public [`/agents`](https://www.fmind.dev/agents) guide documents connection, examples, HTTP contracts, and data boundaries. `get_article` returns canonical Markdown, dates, canonical URL, and section links from the same published article snapshot as HTTP. Drafts are never available through MCP. `compare_llm_hosting` accepts a bounded `parameters` object of string-valued calculator URL inputs; an empty object returns defaults and supported choices. It rejects unknown or invalid inputs rather than silently falling back, then calls the same calculator as the page and returns costs, effective assumptions, units, constraints, dated source links, and a shareable URL. Its `comparison_ready` flag is the calculator's cost/capacity gate, not a claim of production readiness. No LLM, provisioning, benchmark execution, booking, or messaging runs on the server.

The homepage and canonical article routes support `Accept: text/markdown` with `Vary: Accept`; HTML wins ties and is the default. Specific `q=0` exclusions override wildcards. Unsupported preferences fall back to HTML. Fixed article `.md` URLs remain available. Homepage Markdown derives from the canonical public profile and article Markdown uses the existing source renderer. The homepage advertises an RFC 9727 `/.well-known/api-catalog` linkset and `/agents` documentation through `Link` headers; article HTML advertises its Markdown alternate. The profile JSON Schema describes a response representation, so the catalog correctly uses `describedby` rather than presenting it as an OpenAPI specification.

The public skill at `/.well-known/agent-skills/fmind-research/SKILL.md` is packaged under `src/www/agent_skills/`, separate from repository maintenance skills. Its v0.2.0 discovery index at `/.well-known/agent-skills/index.json` hashes the exact served artifact at startup; edit the packaged Markdown and the digest updates automatically. It contains instructions only, without executable scripts. Both skill discovery and the MCP server card are compatibility surfaces, not guarantees of client adoption. WebMCP, DNS-AID, ARD, OAuth registration, Web Bot Auth, hosted chat, embeddings, and vector storage remain out of scope; robots and content-use policy are unchanged.

The homepage, JSON profile, JSON-LD occupation skills, and LLM text derive expertise from the same `EXPERTISE` collection. Both headline lines and the six expertise descriptions are included in `/llms.txt` and `/llms-full.txt`. These are integration surfaces; they do not guarantee search indexing or AI citations.

Use the standard `server/discover` RPC for protocol negotiation and capabilities. The static server card is a compatibility summary of the registered primitives, not an official MCP schema or an A2A Agent Card.

The checked-in `server.json` describes `io.github.fmind/portfolio` in the official MCP Registry. Its version tracks the website release. After verifying that version is serving, publish with the official `mcp-publisher` CLI authenticated as the `fmind` GitHub account:

```bash
mcp-publisher validate server.json
mcp-publisher login github
mcp-publisher publish
```

Verify the published version through the [official Registry API](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.fmind%2Fportfolio). Registry publication is an explicit owner action separate from website deployment.
