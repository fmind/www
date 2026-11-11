# AGENTS.md — www

Python 3.14, Litestar, strict Jinja, Tailwind/DaisyUI, and Granian. No client framework, Node app, or database. Templates are package data; `content/` and `static/` ship beside the locked Python environment.

## Delivery

- **Pass `mise run all` before done**: `mise.toml` defines the task contract ([README](README.md#tasks)). Pass without unresolved warnings and add a regression test for new behavior. Run in the foreground (background runs can OOM), and copy `mise.local.toml` (`IMAGE_PLATFORM = "linux/arm64"` on ARM64) into temporary worktrees so `build:image` avoids QEMU crashes.
- **Iterate fast**: run `mise run build:css` once (startup reads `static/dist/styles.css`), then `uv run --locked pytest tests/<file>.py`.
- **Run affected out-of-gate checks**: run `check:links`, `test:browser:cross`, or `test:lighthouse:local` when relevant.
- **Keep scratch untracked**: tasks write only to ignored paths (`tmp/`, `static/dist/`, `.coverage`, caches); ad hoc scratch goes to OS temporary directories.
- **A `main` push deploys production**: pushing requires deploy authority; published tags are immutable.
- **Preserve the visual style**: the current style (shadows, gradients, hover motion, paired buttons, Tailwind/DaisyUI theme) is an approved exception to [DESIGN.md](https://github.com/fmind/theme/blob/main/DESIGN.md), which still governs new unestablished components. Layout, style, component, or home-page structure changes require owner approval on a proposal branch with before/after screenshots; content edits and new pages reusing existing components do not.
- **Keep Cloud Run scale-to-zero**: [README](README.md#deployment) owns capacity and deploy gates, enforced by `infra/tests/website.tftest.hcl`. Raising capacity or enabling always-on instances requires explicit owner authorization.

## Ownership

- `data.py`, `models.py`, `tags.py`: immutable portfolio, shared types, site registry, closed tag vocabulary.
- `app.py`, `mcp.py`: startup snapshot, routes, lifespan, read-only MCP tools, finite POST-only HTTP transport, discovery.
- `content.py`, `assets.py`, `search.py`: validated articles, static inventory/hashes, BM25 search.
- `news.py`, `scripts/news.py`: validated daily editions in `content/news/`, feed, API, search, exports, and preparation/publish CLI ([news skill](.agents/skills/news/SKILL.md)).
- `publications.py`, `connect.py`: profile JSON/schema, feeds, sitemap, LLM text, public vCard (`/connect` indexed, `/scan` noindex QR).
- `agent_discovery.py`, `agent_skills/`: API catalog, representation negotiation, packaged visitor skill/index (separate from `.agents/` maintenance skills).
- `pages.py`, `rendering.py`, `highlighting.py`, `templates/`: metadata, sole Jinja/trusted-markup boundary, syntax highlighting, layouts, macros.
- `config.py`, `middleware.py`, `markdown.py`, `log.py`, `telemetry.py`, `static.py`, `ranges.py`: config, HTTP/CSP policy, Markdown links, cookieless analytics, logs, optional tracing, inventory-bound static/range delivery.
- `sites/`: hosting input/URL parsing, formulas, charts, formatting, sources, views; `sites/mcp_context_cost/` owns the MCP calculator and measurements. Import from the owning module.
- `scripts/` (excluded from runtime image): manual ops and asset generators (`build_images.py` owns article derivatives). `infra/`: Cloud Run, WIF identities, registry, monitoring, analytics.

## Invariants

- **Validate at boundaries, construct once**: parse external input with chained errors and build the startup snapshot once before serving.
- **Trust markup only in `rendering.py`**: keep Jinja `StrictUndefined` and autoescape; only `rendering.py` trusts validated HTML or guarded JSON-LD.
- **Stay light-only and self-hosted**: Google Sans body, Google Sans Code monospace (`scripts/build_fonts.py`, preserving subset face names). Use existing macros and small nonce-authorized scripts; add no JS bundle without a real module graph.
- **Serve one content-addressed stylesheet**: Tailwind classes live in `src/www/templates/**/*.html`, inputs in `assets/`, public artifacts in `static/` (portrait masters stay outside `static/`; export via `build:portrait`). Pages link `/styles.css?v=<hash>`; CSP forbids inline `<style>`.
- **Publish only validated articles**: `content/articles/<slug>.md` is authoritative; drafts never enter production discovery ([article skill](.agents/skills/article/SKILL.md); keep `content.py:FIGURE_SIZES` aligned with CSS).
- **Register tools explicitly**: list tools in `data.py:SITE_PAGES` with server-owned formulas; MCP rejects invalid values and unknown keys without fallback defaults.
- **Keep analytics cookieless or consented**: first-party analytics stay cookieless and aggregate (empty `country`). GA4 loads only on `www.fmind.dev` after explicit Accept (equally prominent Reject, no ad features/Google signals); keep `/privacy` and CSP Google hosts aligned.
- **Keep the scheduled scanner read-only**: maintain advisory triage in `SECURITY.md`.
- **Keep the CLI contract**: PyPI `fmind` (`github.com/fmind/cli`) consumes `/api/profile` (`PROFILE_SHAPE`), `/api/news` (`NEWS_SHAPE`), `/articles/<slug>.md`, and `/mcp`; update and release the CLI before removing or renaming them.

Procedures live in `.agents/skills/` (`article`, `news`, `site`, `infra`, `release`, `website-analytics`, `finops-analytics`).
