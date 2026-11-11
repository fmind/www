# AGENTS.md — www

Personal website and portfolio of [Médéric Hurier (Fmind)](https://www.fmind.dev/), freelance AI Architect (AI agents, MLOps, security), publishing technical articles, daily tech news, server-rendered decision tools, and read-only agent and MCP endpoints.

Built with Python, Litestar, strict Jinja, Tailwind CSS, DaisyUI, and Granian on Cloud Run (managed with `uv`, `mise`, Playwright, and OpenTofu)—no client framework, Node app, database, or runtime CDN. Templates are package data; `content/` and `static/` ship beside the locked Python environment.

## Delivery

- **Pass `mise run all` before done** ([README](README.md#tasks)): pass without unresolved warnings, add a regression test for new behavior, run in the foreground (background runs can OOM), and copy `mise.local.toml` (`IMAGE_PLATFORM = "linux/arm64"` on ARM64) into worktrees so `build:image` avoids QEMU crashes.
- **Iterate fast**: run `mise run build:css` once (startup reads `static/dist/styles.css`), then `uv run --locked pytest tests/<file>.py`; run `check:links`, `test:browser:cross`, or `test:lighthouse:local` when affected.
- **Keep scratch untracked**: tasks write only to ignored paths (`tmp/`, `static/dist/`, `.coverage`, caches); put ad hoc files in OS temp directories.
- **Preserve the visual style**: current shadows, gradients, hover motion, paired buttons, and Tailwind/DaisyUI theme are an approved exception to [DESIGN.md](https://github.com/fmind/theme/blob/main/DESIGN.md) (which governs new components). Layout, style, component, or home-page changes need owner approval on a proposal branch with before/after screenshots; content edits and new pages reusing existing components do not.
- **Gate deploys and capacity**: pushing `main` deploys production ([README](README.md#deployment)) and requires deploy authority; published tags are immutable. Keep Cloud Run scale-to-zero (`infra/tests/website.tftest.hcl`) unless the owner authorizes higher capacity or always-on instances.

## Invariants

- **Validate at boundaries, construct once**: parse external input with chained errors and build the startup snapshot once before serving.
- **Trust markup only in `rendering.py`**: keep Jinja `StrictUndefined` and autoescape; only `rendering.py` trusts validated HTML or guarded JSON-LD.
- **Stay light-only and self-hosted**: Google Sans and Google Sans Code (`scripts/build_fonts.py`, preserving subset face names), existing macros, and small nonce-authorized scripts; add no JS bundle without a real module graph.
- **Serve one content-addressed stylesheet**: Tailwind scans `src/www/templates/**/*.html`, builds `assets/` into `static/` (portrait masters stay outside `static/`; export via `build:portrait`), and links `/styles.css?v=<hash>` without inline `<style>`.
- **Publish only validated articles**: `content/articles/<slug>.md` is authoritative and drafts stay out of production discovery ([article](.agents/skills/article/SKILL.md); keep `content.py:FIGURE_SIZES` aligned with CSS).
- **Register tools explicitly**: list tools in `data.py:SITE_PAGES` with server-owned formulas ([site](.agents/skills/site/SKILL.md)); MCP rejects invalid values and unknown keys without fallback defaults.
- **Keep analytics cookieless or consented**: first-party analytics stay cookieless and aggregate (no geography); GA4 loads only on `www.fmind.dev` after explicit Accept (equally prominent Reject, no ad features/Google signals), keeping `/privacy` and CSP Google hosts aligned.
- **Keep the scheduled scanner read-only**: maintain advisory triage in [SECURITY.md](SECURITY.md).
- **Keep the CLI contract**: PyPI `fmind` (`github.com/fmind/cli`) consumes `/api/profile` (`PROFILE_SHAPE`), `/api/news` (`NEWS_SHAPE`), `/articles/<slug>.md`, and `/mcp`; update and release the CLI before removing or renaming them.

## Ownership

- `data.py`, `models.py`, `tags.py`: immutable portfolio, shared types, `SITE_PAGES` registry, closed tag vocabulary.
- `app.py`, `mcp.py`: startup snapshot, routes, lifespan, read-only MCP tools, finite POST-only HTTP transport, discovery.
- `content.py`, `assets.py`, `search.py`: articles (`content/articles/`), static inventory/hashes, BM25 search.
- `news.py`, `scripts/news.py`: daily editions (`content/news/`), feed, API, search, exports, and CLI ([news](.agents/skills/news/SKILL.md)).
- `publications.py`, `connect.py`: profile JSON/schema, feeds, sitemap, LLM text, public vCard (`/connect` indexed, `/scan` noindex QR).
- `agent_discovery.py`, `agent_skills/`: API catalog, representation negotiation, packaged visitor skill/index (separate from `.agents/skills/`).
- `pages.py`, `rendering.py`, `highlighting.py`, `templates/`: page metadata, Jinja rendering, syntax highlighting, layouts, macros.
- `config.py`, `middleware.py`, `markdown.py`, `log.py`, `static.py`, `ranges.py`: config, HTTP/CSP policy, Markdown links, analytics, logs, trace correlation, static/range delivery.
- `sites/`: LLM hosting calculator and `sites/mcp_context_cost/` MCP calculator (inputs, formulas, charts, formatting, sources, views; import from the owning module).
- Repo root: `scripts/` (ops and asset generators, excluded from runtime image; `build_images.py` owns article derivatives), `infra/` (Cloud Run, custom domains, WIF, registry, monitoring, billing, analytics; authoritative DNS lives in a separate Cloud DNS project), `.agents/skills/` (`article`, `news`, `site`, `infra`, `release`, `website-analytics`, `finops-analytics`).
