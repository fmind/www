# AGENTS.md — www

Python 3.14, Litestar, strict Jinja, Tailwind/DaisyUI, and Granian. No client framework, Node application, or database. Templates are package data; `content/` and `static/` are deployed beside the locked Python environment.

## Delivery

- **Pass `mise run all` before done**: `mise.toml` is the task contract for local work, hooks, and CI ([README](README.md#tasks)). The gate must pass without unresolved warnings, and new behavior needs a regression test. Run it in the foreground, because background runs have been killed under memory pressure.
- **Iterate with focused tests**: run `mise run build:css` once, because app startup reads the generated stylesheet, then `uv run --locked pytest tests/<file>.py`.
- **Run affected out-of-gate checks**: network link checks, cross-browser tests, and Lighthouse are separate tasks; run those relevant to the change.
- **Keep scratch out of the tracked tree**: tasks write only to ignored paths (`tmp/`, `static/dist/`, `.coverage`, tool caches); ad hoc scratch and review reports go to OS temporary directories and are never committed.
- **A `main` push deploys production**: pushing needs deploy authority; published tags are immutable.
- **Keep the approved visual style**: the site's current style (shadows, gradients, hover motion, paired buttons, and its Tailwind/DaisyUI theme) is an approved exception to [DESIGN.md](https://github.com/fmind/theme/blob/main/DESIGN.md), which still governs new pages and components without an established pattern.
- **Get consent before restyling**: layout, style, component, or home-page structure changes need the owner's OK on a proposal branch with before/after screenshots; content edits and new pages reusing existing components do not.
- **Keep Cloud Run scale-to-zero**: [README](README.md#deployment) owns the capacity and deploy gates, and `infra/tests/website.tftest.hcl` enforces the capacity. Raising capacity or enabling always-on instances needs explicit owner authorization.

## Ownership

- `data.py`, `models.py`, `tags.py`: immutable portfolio, shared types, site registry, closed tag vocabulary.
- `app.py`: startup snapshot, routes, middleware composition, MCP lifespan, teardown.
- `mcp.py`: read-only tools, finite POST-only HTTP transport, capabilities, and discovery.
- `content.py`, `assets.py`, `search.py`: validated publications, static inventory/hashes, BM25 article search.
- `news.py`: validated daily editions in `content/news/` with their feed, API, search, and exports; `scripts/news.py` prepares, drafts, and publishes them ([news skill](.agents/skills/news/SKILL.md)).
- `publications.py`: canonical profile JSON/schema, feeds, sitemap, LLM text; shared by HTTP and MCP.
- `agent_discovery.py`, `agent_skills/`: API catalog, representation negotiation, packaged visitor skill/index; separate from `.agents/` maintenance skills.
- `connect.py`: public vCard; `/connect` is discoverable, `/scan` is a noindex QR utility.
- `pages.py`, `rendering.py`, `highlighting.py`, `templates/`: metadata, sole Jinja/trusted-markup boundary, code highlighting, inherited page layouts and macros.
- `config.py`, `middleware.py`, `markdown.py`, `log.py`, `telemetry.py`: startup configuration, HTTP policy, Markdown link rewriting, privacy-safe analytics, logs, optional tracing.
- `static.py`, `ranges.py`: inventory-bound static and conditional/range delivery.
- `sites/`: hosting input/URL parsing, formulas, charts, formatting, sources, and views; `sites/mcp_context_cost/` owns the MCP calculator and its dated measurements. Import from the owning module.
- `scripts/`: manual operations and asset generators (`build_images.py` owns article-image derivatives), excluded from the runtime image. `infra/`: service, identities, registry, monitoring, analytics.

## Invariants

- **Validate at boundaries, construct once**: parse external input at boundaries with chained errors, and construct the startup snapshot (articles, news, search, assets, publications, renderer, MCP) once before serving.
- **Trust markup only in `rendering.py`**: keep Jinja `StrictUndefined` and autoescape. Only `rendering.py` may trust validated article/biography HTML or guarded JSON-LD.
- **Stay light-only and self-hosted**: Google Sans is body text, Google Sans Code is code. Use existing macros and small nonce-authorized page interactions; do not add a JS bundle without a real module graph.
- **Serve one content-addressed stylesheet**: Tailwind classes belong in `src/www/templates/**/*.html`. Authored build inputs go in `assets/`; final public artifacts go in `static/`. Pages link `/styles.css?v=<hash>` (Tailwind output plus syntax colors, served from memory); CSP allows no inline `<style>`.
- **Publish only validated articles**: `content/articles/<slug>.md` is the authoritative body, and drafts never enter production discovery. Tags, images, captions, and figure sizes follow the [article skill](.agents/skills/article/SKILL.md); keep `content.py:FIGURE_SIZES` aligned with article CSS.
- **Register tools explicitly**: register tools in `data.py:SITE_PAGES` with server-owned formulas; MCP tools reject invalid values and unknown argument keys instead of applying defaults.
- **Build fonts only with the generator**: use `scripts/build_fonts.py` and preserve subset-specific face names.
- **Keep portrait masters private**: keep them outside `static/`; export with `build:portrait`.
- **Keep analytics cookieless or consented**: first-party analytics stay cookieless and aggregate (empty `country` until a trusted geography boundary exists). Google Analytics 4 loads only on www.fmind.dev after an explicit Accept (Reject equally prominent, no ad features or Google signals); keep `/privacy` and CSP Google hosts in step.
- **Keep the scheduled image scanner read-only**: maintain advisory triage in `SECURITY.md`.
- **Keep the CLI contract**: the PyPI `fmind` CLI (github.com/fmind/cli) consumes the `/api/profile` keys in its `PROFILE_SHAPE`, the `/api/news` keys in its `NEWS_SHAPE`, `/articles/<slug>.md`, and the `/mcp` transport; release a CLI update before removing or renaming any of them.

Task procedures live in `.agents/skills/` (`article`, `news`, `site`, `infra`, `release`, `website-analytics`, `finops-analytics`).
