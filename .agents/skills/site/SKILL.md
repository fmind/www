---
name: site
description: Build source-backed decision tools in the existing Litestar/Jinja site with server-owned formulas and shared discovery. Use for /sites/ work.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Decision Pages

Build within the existing Litestar/Jinja application, with Python as the sole formula implementation. Keep each tool minimal: few inputs, one headline answer, and every section open (no `<details>`), with setup notes directly above "Method and limitations". Add an input only when the headline answer needs it, and reuse `src/www/sites/data.py:API_BASELINES` instead of a second price table.

1. **Verify and snapshot sources**: check volatile prices, licenses, and benchmarks against current primary sources. Store immutable dated snapshots under `src/www/sites/`; separate sourced facts from editable assumptions.
1. **Register the page**: add it to `src/www/data.py:SITE_PAGES`, then wire its route, template, metadata, and view through `src/www/app.py`, `src/www/pages.py`, and `src/www/rendering.py:PageTemplate` (feeds sitemap, JSON, LLM text, MCP, and article relationships).
1. **Keep parsing, formulas, and views in `src/www/sites/`**: reject non-finite or out-of-range values; page fallback defaults must show validation messages, while MCP invalid input must fail. Round up whole billable resources.
1. **Isolate tool modules**: keep hosting modules in place; independent tools live in a named subpackage such as `mcp_context_cost/`. Preserve its measurement provenance and present reference token counts as estimates, never actual provider usage.
1. **Reuse templates and GET forms**: use the central renderer, shared macros, and a native GET form for shareable scenarios (JavaScript is progressive enhancement only). Keep assumptions, units, source dates, capacity limits, and pilot requirements visible.
1. **Test and verify**: test calculations, invalid inputs, handlers, 404s, metadata, and discovery. Verify keyboard/no-JavaScript behavior, mobile/desktop reflow, and light mode even with a dark system preference. Run `mise run all`.

Use only self-hosted assets and the existing trusted-markup boundary. Planning estimates do not establish measured performance, production readiness, or legal permission. Do not add client formula copies, runtime CDNs, tracking, or a separate microsite.
