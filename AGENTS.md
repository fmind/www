# AGENTS.md — www

Python 3.14, Litestar, strict Jinja, Tailwind/DaisyUI, and Granian. No client framework, Node application, or database. Templates are package data; `content/` and `static/` are deployed beside the wheel.

## Delivery

- `mise.toml` is the canonical task contract for local work, hooks, and CI. See [README](README.md#tasks) and `mise tasks` for commands.
- Definition of done: `mise run all` passes without unresolved warnings; infrastructure changes also pass `mise run check:tofu`. New behavior needs a regression test.
- `all` runs format, check, package/CSS build, pytest (branch coverage ≥85%), OCI build/scan/smoke, Chromium install, and browser journeys sequentially. Docker Engine/Buildx and first-run network access are required; no cloud credentials are needed.
- Network link checks, cross-browser tests, and Lighthouse are separate tasks. Run those relevant to the change; never weaken checks to get a green release.
- Inspect Git status/diffs and preserve unrelated work and staged selections. Use OS temporary directories for agent scratch; no repository-local review reports. Remove only task-owned temporary artifacts.
- Commit, push, release, deploy, apply infrastructure, and spend require owner authorization. Reuse authority already given. Use Conventional Commits without attribution; published tags are immutable.
- Keep Cloud Run **service and revision minimum instances at 0**, maximum 5, and request-based CPU (`cpu_idle = true`). Raising capacity or enabling always-on instances requires explicit owner authorization.
- OpenTofu owns service settings; CI owns only the image digest. A `main` deployment must scan and smoke-test its pushed immutable digest before rollout, then verify ready revision, traffic, health, and errors.

## Ownership

- `data.py`, `models.py`, `tags.py`: immutable portfolio, shared types, site registry, closed tag vocabulary.
- `app.py`: startup snapshot, routes, middleware composition, MCP lifespan, teardown.
- `content.py`, `images.py`, `assets.py`: validated publications, media derivatives, static inventory/hashes.
- `publications.py`: canonical profile JSON/schema, feeds, sitemap, LLM text; shared by HTTP and MCP.
- `agent_discovery.py`, `agent_skills/`: API catalog, representation negotiation, packaged visitor skill/index; separate from `.agents/` maintenance skills.
- `connect.py`: public vCard; `/connect` is discoverable, `/scan` is a noindex QR utility.
- `pages.py`, `rendering.py`, `templates/`: metadata, sole Jinja/trusted-markup boundary, inherited page layouts and macros.
- `middleware.py`, `log.py`, `telemetry.py`: HTTP policy, privacy-safe analytics, logs, optional tracing.
- `static.py`, `ranges.py`: inventory-bound static and conditional/range delivery.
- `sites/`: input/URL parsing, formulas, charts, formatting, immutable sources, and views. Import from the owning module.
- `scripts/`: manual operations and asset generators, excluded from the runtime image. `infra/`: service, identities, registry, monitoring, analytics.

## Invariants

- Parse external input at boundaries and fail with contextual chained errors. Construct validated articles, search, assets, publications, renderer, and MCP once; requests must not observe partial state.
- Keep Jinja `StrictUndefined` and autoescape. Only `rendering.py` may trust validated article/biography HTML, CSS, or guarded JSON-LD.
- Keep the site light-only and assets self-hosted. Google Sans is body text, Google Sans Code is code. Use existing macros and small nonce-authorized page interactions; do not add a JS bundle without a real module graph.
- Tailwind classes belong in `src/www/templates/**/*.html`. Authored build inputs go in `assets/`; final public artifacts go in `static/`.
- The validated article collection is the only publication source; drafts never enter production discovery. Current Markdown is the authoritative article body.
- Register tools in `data.py:SITE_PAGES` and wire routes/templates/views explicitly. Formulas remain server-owned. MCP calculator input rejects invalid values instead of silently applying defaults.
- Tags require a `tags.py` entry, matching CSS rule, and article use. Generate reviewed image derivatives and provenance lock after media changes; `check:images` never writes.
- Keep `content.py:FIGURE_SIZES` aligned with article CSS. Figures never pan; captions require repeated alt text. Diagram labels must remain about 12px or larger at 1280px and height at most about 1300px.
- Build fonts only with `scripts/build_fonts.py`; keep required assets, CSS faces, and template preloads synchronized. Preserve subset-specific face names. Keep private portrait masters outside `static/`; export with `build:portrait`.
- Analytics remain cookieless and aggregate, with 180-day expiry and empty `country` until a trusted geography boundary exists. The scheduled image scanner stays read-only; maintain advisory triage in `SECURITY.md`.

Task procedures live in `.agents/skills/`: `article`, `site`, `infra`, `release`, `website-analytics`, and `finops-analytics`. Keep instructions concise and avoid repeating the README or task definitions.
