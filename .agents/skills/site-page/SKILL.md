---
name: site-page
description: Add or revise a source-backed interactive decision page under /sites/ while preserving shared discovery, metadata, server-rendered calculations, and project quality gates. Use for site-page work.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Build a Site Page

Create one focused, source-backed decision tool inside the existing Go, Templ, and Tailwind application.

## Workflow

1. Verify volatile claims and prices against current primary sources. Record the snapshot date and link every authority on the page.
1. Add the page to `templates.SITE_PAGES`; this registry feeds routing metadata, the sitemap, `llms.txt`, JSON, and MCP discovery.
1. Keep inputs and calculations in a small root Go file. Parse query values at the boundary, enforce ranges, fail closed to explicit defaults, and use whole billable resources.
1. Build the interface in a focused `templates/*.templ` component. Reuse `Layout`, project typography, DaisyUI primitives, spacing, navigation, and metadata helpers.
1. Use a native GET form so assumptions are shareable and Go remains the only formula implementation. Add client JavaScript only when server rendering cannot meet the interaction.
1. Show assumptions, units, cost boundaries, operational caveats, source freshness, and the decisions that still require a pilot.
1. Add calculation tests and real-handler tests for the canonical page, invalid input, 404 behavior, structured data, and discovery surfaces.
1. Run the project gates and inspect desktop and mobile layouts:

   ```bash
   mise run format
   mise run check
   mise run test
   mise run build
   ```

## Gotchas

- `assets/` contains authored inputs; `static/` contains generated or final public assets.
- Tailwind classes belong in `.templ` files so the source scanner sees them.
- Estimates must separate sourced facts from editable assumptions; do not imply benchmark precision without a measured workload.
- License labels are planning signals, not legal conclusions. Link the model terms and require review where restrictions apply.
- Keep operational GCP identifiers stable unless the task explicitly includes a live infrastructure migration.

## Official Skills

- Use [technical-research](~/.agents/skills/technical-research/SKILL.md) for volatile model, cloud, or pricing claims.
- Use [product-design-review](~/.agents/skills/product-design-review/SKILL.md) for responsive and accessibility review.
- Use [playwright](~/.agents/skills/playwright/SKILL.md) for browser verification.

## Documentation

- [Templ documentation](https://templ.guide/)
- [Google Cloud pricing](https://cloud.google.com/products/calculator)
- [Artificial Analysis models](https://artificialanalysis.ai/models)
