# AGENTS.md — www

Python 3.14, Litestar, strict Jinja, Tailwind/DaisyUI, and Granian. No client framework, Node application, or database. Templates are package data; `content/` and `static/` are deployed beside the wheel.

## Delivery

- **Use the mise task contract**: `mise.toml` serves local work, hooks, and CI. See [README](README.md#tasks) and `mise tasks` for commands, and [README](README.md#development) for prerequisites.
- **Pass `mise run all` before done**: it must pass without unresolved warnings; infrastructure changes also pass `mise run check:tofu`, and new behavior needs a regression test. Run it in the foreground, because background runs have been killed under memory pressure.
- **Iterate with focused tests**: run `mise run build:css` once, because app startup reads the generated stylesheet, then `uv run --locked pytest tests/<file>.py`.
- **Run affected out-of-gate checks**: network link checks, cross-browser tests, and Lighthouse are separate tasks; run those relevant to the change.
- **Keep scratch out of the tracked tree**: tasks write their outputs only to the ignored `tmp/`; ad hoc scratch and review reports go to OS temporary directories, and no review report is committed.
- **A `main` push deploys production**: pushing needs deploy authority; published tags are immutable.
- **Keep the approved visual style**: the site's current style (shadows, gradients, hover motion, paired buttons, and its Tailwind/DaisyUI theme) is an approved exception to `~/.agents/DESIGN.md`; DESIGN.md still governs new pages and components where the site has no established pattern.
- **Get consent before restyling**: layout, style, component, or home-page structure changes need the owner's OK on a proposal branch with before/after screenshots. Content edits inside existing components are fine; new pages reuse existing components unchanged.
- **Keep Cloud Run scale-to-zero**: service and revision minimum instances 0, maximum 5, and request-based CPU (`cpu_idle = true`). Raising capacity or enabling always-on instances needs explicit owner authorization.
- **CI owns only digest and traffic**: OpenTofu owns service settings. A `main` deployment must scan and smoke-test its pushed immutable digest, verify a no-traffic `candidate` revision, then promote exactly that revision and verify ready revision, traffic, and health; review error logs separately with the owner identity.

## Ownership

- `data.py`, `models.py`, `tags.py`: immutable portfolio, shared types, site registry, closed tag vocabulary.
- `app.py`: startup snapshot, routes, middleware composition, MCP lifespan, teardown.
- `mcp.py`: read-only tools, finite HTTP transport, capabilities, and discovery. Every non-POST method returns 405 with `Allow: POST`, so GET/HEAD never open idle notification streams; retain SDK host/origin validation.
- `content.py`, `images.py`, `assets.py`, `search.py`: validated publications, media derivatives, static inventory/hashes, BM25 article search.
- `publications.py`: canonical profile JSON/schema, feeds, sitemap, LLM text; shared by HTTP and MCP.
- `agent_discovery.py`, `agent_skills/`: API catalog, representation negotiation, packaged visitor skill/index; separate from `.agents/` maintenance skills.
- `connect.py`: public vCard; `/connect` is discoverable, `/scan` is a noindex QR utility.
- `pages.py`, `rendering.py`, `highlighting.py`, `templates/`: metadata, sole Jinja/trusted-markup boundary, code highlighting, inherited page layouts and macros.
- `config.py`, `middleware.py`, `markdown.py`, `log.py`, `telemetry.py`: startup configuration, HTTP policy, Markdown link rewriting, privacy-safe analytics, logs, optional tracing.
- `static.py`, `ranges.py`: inventory-bound static and conditional/range delivery.
- `sites/`: hosting input/URL parsing, formulas, charts, formatting, sources, and views; `sites/mcp_context_cost/` owns the MCP calculator and its dated measurements. Import from the owning module.
- `scripts/`: manual operations and asset generators, excluded from the runtime image. `infra/`: service, identities, registry, monitoring, analytics.

## Invariants

- **Validate at boundaries, construct once**: parse external input at boundaries and fail with contextual chained errors. Construct validated articles, search, assets, publications, renderer, and MCP once; requests must not observe partial state.
- **Trust markup only in `rendering.py`**: keep Jinja `StrictUndefined` and autoescape. Only `rendering.py` may trust validated article/biography HTML or guarded JSON-LD.
- **Stay light-only and self-hosted**: Google Sans is body text, Google Sans Code is code. Use existing macros and small nonce-authorized page interactions; do not add a JS bundle without a real module graph.
- **Serve one content-addressed stylesheet**: Tailwind classes belong in `src/www/templates/**/*.html`. Authored build inputs go in `assets/`; final public artifacts go in `static/`. Pages link `/styles.css?v=<hash>` (Tailwind output plus syntax colors, served from memory); CSP allows no inline `<style>`.
- **Publish only validated articles**: the validated article collection is the only publication source; drafts never enter production discovery. Current Markdown is the authoritative article body.
- **Register tools explicitly**: register tools in `data.py:SITE_PAGES` and wire routes/templates/views explicitly. Formulas remain server-owned. MCP tools reject invalid values and unknown argument keys instead of silently applying defaults.
- **Keep articles reviewed**: tags, image derivatives, captions, and figure sizes follow the [article skill](.agents/skills/article/SKILL.md); keep `content.py:FIGURE_SIZES` aligned with article CSS, and `check:images` never writes.
- **Build fonts only with the generator**: use `scripts/build_fonts.py`; keep required assets, CSS faces, and template preloads synchronized. Preserve subset-specific face names.
- **Keep portrait masters private**: keep them outside `static/`; export with `build:portrait`.
- **Keep analytics cookieless or consented**: first-party analytics remain cookieless and aggregate, with 180-day expiry and empty `country` until a trusted geography boundary exists. Google Analytics 4 (`google_analytics_id`) loads only on www.fmind.dev after an explicit Accept in `partials/consent.html`, with rejection as easy as acceptance and no advertising features or Google signals; never load it before consent, and keep `/privacy` and the CSP's Google hosts in step with it.
- **Keep the scheduled image scanner read-only**: maintain advisory triage in `SECURITY.md`.
- **Keep the CLI contract**: the PyPI `fmind` CLI (github.com/fmind/cli) consumes the `/api/profile` keys in its `PROFILE_SHAPE`, `/articles/<slug>.md`, and the `/mcp` transport; release a CLI update before removing or renaming any of them.

Task procedures live in `.agents/skills/`: `article`, `site`, `infra`, `release`, `website-analytics`, and `finops-analytics`. Keep instructions concise and avoid repeating the README or task definitions.
