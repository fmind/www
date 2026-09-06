---
name: site
description: Build source-backed decision tools in the existing Litestar/Jinja site with server-owned formulas and shared discovery. Use for /sites/ work.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Build a Site Page

Add one focused decision tool to the existing Litestar, Jinja, Tailwind, and DaisyUI application; do not create a separate microsite.

## Workflow

1. Verify volatile claims, prices, licenses, and benchmarks against current primary sources. Store immutable source snapshots and dates under `src/www/sites/`, link every authority on the page, and separate sourced facts from editable assumptions.
1. Add the page to `src/www/data.py:SITE_PAGES`. The registry feeds metadata, sitemap, LLM text, JSON, MCP discovery, and article relationships. Wire the Litestar route, template, and view builder explicitly through `src/www/app.py`, and use the `src/www/pages.py` metadata builders.
1. Put typed view models and calculations in focused modules under `src/www/sites/`. Parse query values at the boundary, reject non-finite or out-of-range values, fail closed to explicit defaults with visible validation messages, and round up whole billable resources.
1. Add a page template under `src/www/templates/pages/` and shared components under `src/www/templates/macros/` or `partials/`. Reuse base inheritance, navigation, typography, DaisyUI primitives, spacing, metadata, and the central `src/www/rendering.py` renderer.
1. Use a native GET form so scenarios are shareable and Python remains the sole formula implementation. Add JavaScript only for progressive enhancement that cannot be expressed by the server response; the page must remain useful without it.
1. Show assumptions, units, cost boundaries, source freshness, capacity/quality/latency caveats, and decisions that still require a measured pilot. Never present a planning estimate as benchmark precision.
1. Add deterministic calculation and handler tests covering canonical output, invalid input, 404 behavior, structured data, and every discovery surface. Extend pinned Playwright journeys for desktop/light and mobile/dark.
1. Run and inspect the complete local gates:

   ```bash
   mise run format
   mise run check
   mise run test
   mise run test:browser
   ```

## Gotchas

- `assets/` contains authored build inputs; `static/` contains compiled or final public assets copied into the production image.
- Tailwind classes belong in `src/www/templates/**/*.html`, the tree scanned by `assets/css/input.css`.
- Keep Jinja autoescape and `StrictUndefined` enabled. Do not add a raw `Markup` boundary; only `src/www/rendering.py` may trust validated HTML, CSS, and JSON-LD.
- Reuse package macros instead of duplicating cards, icons, or article links. Includes must not rely on hidden page-specific context.
- Preserve native focus, labels, validation summaries, landmarks, keyboard behavior, and reduced-motion behavior. Verify both narrow and wide layouts.
- Keep all static assets self-hosted. Do not add runtime CDNs, widgets, SDKs, client formula copies, cookies, or tracking.
- License labels are planning signals, not legal conclusions. Link terms and require review where restrictions apply.
- Keep operational GCP identifiers unchanged unless the task explicitly includes an authorized live infrastructure migration.

## Official Skills

- Use [technical-research](~/.agents/skills/technical-research/SKILL.md) for volatile model, cloud, or pricing claims.
- Use [product-design-review](~/.agents/skills/product-design-review/SKILL.md) for responsive and accessibility review.
- Use [playwright](~/.agents/skills/playwright/SKILL.md) for browser verification.

## Documentation

- [Litestar](https://docs.litestar.dev/)
- [Jinja](https://jinja.palletsprojects.com/)
- [Google Cloud pricing](https://cloud.google.com/products/calculator)
- [Artificial Analysis models](https://artificialanalysis.ai/models)
