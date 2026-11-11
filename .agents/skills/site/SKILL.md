---
name: site
description: Build source-backed decision tools under /sites/ with server-owned Python formulas and MCP parity.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Decision Pages

Build inside the existing Litestar/Jinja app with Python as the sole formula owner. Keep tools minimal: few inputs, one headline answer, all sections open (no `<details>`), setup notes directly above "Method and limitations", and shared API rates from `src/www/sites/data.py:API_BASELINES`.

1. **Snapshot sources**: verify prices, licenses, and recipes against primary sources; store dated immutable snapshots under `src/www/sites/`, separating sourced facts from editable assumptions.
1. **Register the page**: add to `src/www/data.py:SITE_PAGES` and wire `src/www/app.py`, `src/www/pages.py`, and `src/www/rendering.py:PageTemplate` (feeds sitemap, profile JSON, `llms.txt`, MCP, and article links).
1. **Keep formulas in `src/www/sites/`**: reject non-finite or out-of-range inputs (HTML shows validation notices on fallback defaults; MCP fails closed) and round up whole billable resources.
1. **Isolate tool packages**: keep LLM hosting modules at root and independent tools in subpackages (`mcp_context_cost/`), framing reference token counts as estimates rather than provider billing.
1. **Reuse templates and GET forms**: use `Renderer`, shared macros, and native GET forms (JS is progressive enhancement only); surface assumptions, units, snapshot dates, capacity limits, and pilot gates.
1. **Verify**: test math, invalid inputs, routes, 404s, metadata, discovery, keyboard/no-JS use, mobile/desktop reflow, and forced light mode; pass `mise run all`.

Keep assets self-hosted inside the trusted-markup boundary; add no client formula copies, runtime CDNs, tracking, or microsites.
