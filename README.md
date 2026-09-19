# www

<!-- mcp-name: io.github.fmind/portfolio -->

[Médéric Hurier (Fmind)](https://www.fmind.dev/), freelance AI Architect specializing in AI agents, MLOps, and security. The website is server-rendered Python: Litestar, strict Jinja, Tailwind CSS v4, DaisyUI v5, and Granian. Small page-specific JavaScript controllers enhance native navigation and forms. There is no client framework, application database, runtime CDN, cookie, or client-side analytics.

## Development

Requires [mise](https://mise.jdx.dev/), Docker Engine with Buildx, and network access for initial tool/browser installation and image/scanner downloads. Python 3.14.7 and the remaining toolchain are pinned in `mise.toml` and `mise.lock`; `.mise/locks/` records the browser tools' transitive npm dependencies and must be committed with lock updates.

```bash
mise install
mise run install
mise run watch
```

Open `http://localhost:8080`; use `PORT=8081 mise run watch` for another port. `.env.example` lists runtime variables; `.env` files are not loaded automatically. The default environment is `development`; production sets `ENVIRONMENT=production`. Reload watches `src/`, `content/`, and `static/`; restart after environment/configuration changes.

`src/www/app.py` constructs the immutable startup snapshot and routes. `src/www/__main__.py` starts Granian. Templates are wheel package data; the image copies the separate `content/` and `static/` trees beside the locked environment. [AGENTS.md](AGENTS.md) maps module ownership and invariants.

## Content and design

`src/www/data.py` supplies portfolio facts, service availability, HTML, JSON/JSON-LD, vCard, and LLM text. Preserve the owner's voice and factual claims across these surfaces.

The light-only [fmind/theme](https://github.com/fmind/theme) palette uses white, light gray, charcoal, and blue `#174EA6`. `assets/css/input.css` owns interface colors; `src/www/highlighting.py` owns syntax colors. Tests enforce the palette with explicit company-brand exceptions. Tailwind scans `src/www/templates/**/*.html`.

Fonts are self-hosted Google Sans and Google Sans Code subsets. The font generator pins upstream releases, removes reserved logo ligatures, and preserves timestamps. Public branding masters are `/logo.png` and `/banner.png`. Keep private portrait originals outside `static/`; `build:portrait` exports `/portrait.jpg` with orientation/ICC preserved and personal metadata removed.

Share `/connect` at events; it offers LinkedIn, a vCard, and the full website. `/scan` is a noindex QR utility. The UTF-8 vCard 3.0 derives public professional details and a sanitized portrait from portfolio data, without a phone number, street address, birthday, or precise coordinates.

Articles in `content/articles/` use strict TOML frontmatter. Their validated collection feeds every publication surface, excluding drafts in production. `build:images` generates responsive WebP derivatives and the SHA-256 provenance lock; `check:images` never writes. Figures fit the 1280px column; code highlighting is server-side. Follow the [article skill](.agents/skills/article/SKILL.md).

Decision tools use typed Python formulas, native GET forms, dated sources, and explicit planning limits. Register them in `data.py:SITE_PAGES`; follow the [site skill](.agents/skills/site/SKILL.md). See [AGENTS.md](AGENTS.md) for module ownership and invariants.

## Tasks

`mise.toml` is the canonical contract used by hooks and CI; `mise tasks` lists all tasks and aliases.

| Command                                                    | Purpose                                                                                                     |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `mise run all`                                             | Format, checks, build, pytest, OCI build/scan/smoke, Chromium install, browser journeys                     |
| `mise run check`                                           | Metadata/locks, Ruff, ty, dprint, secrets, dependencies, Docker/IaC/workflow scans, image provenance, typos |
| `mise run test`                                            | Offline pytest with branch coverage ≥85% and warnings as errors                                             |
| `mise run check:tofu`                                      | Backend-free provider validation, tflint, and mocked infrastructure plan tests                              |
| `mise run check:links`                                     | Network-dependent external-link audit; scheduled separately from merge gates                                |
| `mise run test:browser`                                    | Desktop/mobile Chromium journeys                                                                            |
| `mise run test:browser:cross`                              | Focused Firefox/WebKit journeys                                                                             |
| `mise run test:lighthouse:local`                           | Temporary local server and strict ten-audit portfolio matrix                                                |
| `mise run build`                                           | Production CSS, wheel, and source distribution                                                              |
| `mise run check:image`                                     | Build and scan `tmp/www-image.tar`                                                                          |
| `mise run test:image [digest-ref]`                         | Smoke-test the existing archive or exact remote digest                                                      |
| `mise run check:image:deployed`                            | Resolve and scan every image receiving Cloud Run traffic                                                    |
| `mise run build:branding` / `build:fonts` / `build:images` | Regenerate reviewed assets on demand                                                                        |
| `mise run build:portrait <private-master.jpg>`             | Export the sanitized public portrait                                                                        |
| `mise run deploy <digest-ref>`                             | Manual image-only rollout/rollback; production-mutating                                                     |

`all` runs sequentially and reuses build outputs and its image archive. It requires Docker/Buildx but no cloud credentials. Asset generators, `clean`, watchers, live scans, and deployment run only on demand; `clean` deletes generated output.

Lighthouse stays separate: install Chromium, then use `mise run test:lighthouse -- --base-url <origin> --mode portfolio` for ten desktop/mobile audits of the portfolio, contact, privacy, and archive indexes. `smoke` runs four audits; default `full` covers the sitemap plus 48 stress audits. Run performance audits without concurrent builds or font generation; keep exact per-page scores.

Cross-browser checks require `install:browser:cross` and [Playwright system libraries](https://playwright.dev/docs/browsers#system-dependencies), or a matching official browser container via `PW_TEST_CONNECT_WS_ENDPOINT`. The [weekly/manual quality workflow](.github/workflows/quality.yml) provisions ephemeral runners and retains evidence for 14 days. Run browser suites sequentially because they share local port 8096. Set `BROWSER_BASE_URL=https://www.fmind.dev` for production journeys; local servers otherwise start and stop automatically.

## Deployment

Cloud Run serves <https://www.fmind.dev/> in project `www-fmind-dev`, region `europe-west1`. [infra/](infra/) owns service settings, registry, keyless identities, alerts, and analytics. Keep **minimum instances at 0 at both service and revision levels**, maximum 5, and request-based CPU. The qualified runtime uses 1 CPU, 512 MiB, concurrency 8, a 30-second request timeout, and six startup attempts five seconds apart. Maximum instances limits scaling; it is not a hard billing cap.

A `main` push runs the full gate, builds a non-root image with SBOM/provenance, pushes it, scans and smoke-tests its immutable digest, then deploys through branch- and numeric-ID-restricted Workload Identity Federation. `test:deployed` verifies that `IMAGE_REF` and `GITHUB_SHA` match the ready revision receiving 100% of traffic, preserves scale-to-zero checks, and probes public health/profile/MCP discovery. Error-log review remains an independent release check because the deployer has no log-reading role. OpenTofu ignores the image field; CI never applies infrastructure. Actions are SHA-pinned and Dependabot maintains ecosystem updates.

Infrastructure changes require a reviewed saved plan and owner-authorized apply through the [infra skill](.agents/skills/infra/SKILL.md). Remote state is `gs://www-fmind-dev-tfstate/infra/state`; its bootstrap bucket is managed separately and requires versioning and enforced public-access prevention. Reconcile service changes before deploying the application.

For manual rollout/rollback, `mise run deploy europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev@sha256:<64-lowercase-hex>` accepts one qualified repository digest. Tags, foreign repositories, and extra flags fail before `gcloud`. First run `check:image:digest <digest-ref>` and `test:image <digest-ref>` for a new digest. Verify ready revision, 100% traffic, matching commit/digest, health, discovery, browser journeys, and error logs. Keep the preceding qualified digest for rollback. Semver publication follows the [release skill](.agents/skills/release/SKILL.md).

[SECURITY.md](SECURITY.md) owns vulnerability reporting and residual advisory review. Deployment blocks fixable HIGH/CRITICAL vulnerabilities and secrets; scheduled scanning retains unfixed findings with a separate read-only identity. GitHub dependency alerts, security updates, secret scanning, and push protection are enabled; main rejects deletion and force pushes.

## Analytics and privacy

`/privacy` describes the data flow. HTML responses emit aggregate path/status, referrer hostname, validated UTM tokens, and a heuristic bot flag. Redirects are excluded; geography remains empty. BigQuery partitions expire after 180 days without duplicate Cloud Logging retention. Analytics omit IPs, raw user agents, full referrers, cookies, sessions, and trace identifiers. Separate private Cloud Run operational logs may contain IPs, user agents, and full URLs and expire after 30 days.

Use the [website-analytics skill](.agents/skills/website-analytics/SKILL.md) or `uv run --locked python -m scripts.website_analytics` for a bounded, no-charge report. Defaults compare the last seven complete days with the previous seven in `Europe/Paris`; `--days`, exclusive `--end-date`, and `--timezone` override them. Reports fail on incomplete/changing data and are not unique-visitor or conversion measurements. Keep production reports out of Git.

Tracing is opt-in through standard `OTEL_EXPORTER_OTLP_*` variables. Operational logs correlate trace/span IDs; analytics omit them.

Use [finops-analytics](.agents/skills/finops-analytics/SKILL.md) for cloud cost, budget, and optimization reviews. OpenTofu manages the billing APIs and private EU dataset `billing_export`. Activate **Standard usage cost** in Cloud Console → Billing → Billing export, selecting project `www-fmind-dev` and this dataset; leave other export types disabled. The account-wide export needs project-filtered, on-demand queries with dry runs and a 100 MiB scan cap. Verify activation and table arrival before claiming costs are available; initial backfill can take five days.

## Agent access

The public [/agents](https://www.fmind.dev/agents) guide is the integration reference. Connect an MCP client to `https://www.fmind.dev/mcp` for read-only, unauthenticated portfolio, publication, search, service, and hosting-comparison tools. Browser requests have same-origin protection; request bodies are bounded. Tools never provision, run LLMs, book services, or send messages.

`/api/profile` and its JSON Schema share the startup snapshot with LLM text, feeds, sitemap, and JSON-LD. Homepage/article routes support `Accept: text/markdown` and `Vary: Accept`; HTML wins ties. Fixed article `.md` URLs remain available. The API catalog, MCP server card, and packaged visitor skill expose discovery; use `server/discover` for protocol negotiation. Visitor skills are separate from repository maintenance skills.

Keep identity, Luxembourg work location, and service availability in `src/www/data.py`. The homepage, profile JSON/MCP, and LLM summaries share these facts. Article HTML and Markdown identify the author; `/llms-full.txt` retains each article's dates and canonical link. Validate search appearance with the local Lighthouse task; indexing and ranking require separate Search Console evidence after deployment.

`server.json` tracks the website release for `io.github.fmind/portfolio`. MCP Registry publication is a separate owner action after live verification: `mcp-publisher validate server.json`, `mcp-publisher login github`, then `mcp-publisher publish`. Verify through the [Registry API](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.fmind%2Fportfolio). Discovery does not guarantee client adoption or AI citations.
