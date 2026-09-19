---
name: site
description: Build source-backed decision tools in the existing Litestar/Jinja site with server-owned formulas and shared discovery. Use for /sites/ work.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Decision Pages

Build within the existing Litestar/Jinja application, with Python as the sole formula implementation.

1. Verify volatile prices, licenses, and benchmarks against current primary sources. Store immutable dated snapshots under `src/www/sites/`; separate sourced facts from editable assumptions.
1. Register the page in `src/www/data.py:SITE_PAGES`, then wire its route, template, metadata, and view through `src/www/app.py` and `src/www/pages.py`. The registry feeds sitemap, JSON, LLM text, MCP, and article relationships.
1. Keep typed parsing, formulas, and view composition in their owning `src/www/sites/` modules. Reject non-finite/out-of-range values; page fallback defaults must show validation messages, while MCP invalid input must fail. Round up whole billable resources.
1. Reuse templates, macros, and the central renderer. Use a native GET form for shareable scenarios; JavaScript provides progressive enhancement only. Keep assumptions, units, source dates, capacity limits, and pilot requirements visible.
1. Test calculations, invalid inputs, handlers, 404s, metadata, and discovery. Verify keyboard/no-JavaScript behavior, mobile/desktop reflow, and light mode even with a dark system preference. Run `mise run all`.

Use only self-hosted assets and the existing trusted-markup boundary. Planning estimates do not establish measured performance, production readiness, or legal permission. Do not add client formula copies, runtime CDNs, tracking, or a separate microsite.
