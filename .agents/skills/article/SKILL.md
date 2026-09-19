---
name: article
description: Publish, revise, or retire a www.fmind.dev article with strict metadata, media, and owner gates. Use for authorized changes under content/articles/.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Articles

The current `content/articles/<slug>.md` is the authoritative body. Revise or retire published content only within owner authorization; publication is separate from local editing.

1. Validate strict TOML frontmatter: matching filename/slug, required fields, typed dates and `draft`, HTTPS provenance. Site-owned articles omit `canonical`; external copies use `syndicated`.
1. Use tags from `src/www/tags.py`. A new tag needs a matching CSS rule and at least one article use. Fence code with a language.
1. Keep source images near the 2.4MP budget. Run `mise run build:images`, review the result, and commit derivatives plus `assets/image-derivatives.json`; `check:images` verifies their hashes and encoder recipe without writing.
1. Inspect desktop/mobile rendering. Figures fit the 1280px column without horizontal panning; diagrams need apparent labels around 12px or larger and height around 1300px or less at that width. Fix unreadable diagrams at their source.
1. Run `mise run all` and `mise run check:links`; add only legitimate spelling exceptions to `typos.toml`. Use the [release skill](../release/SKILL.md) when publication is authorized.

`src/www/content.py` disables raw HTML, normalizes headings, and folds a following paragraph into a caption only when its text repeats the image alt. Keep `FIGURE_SIZES` aligned with article CSS. The validated collection feeds HTML, Atom, sitemap, LLM text, JSON, search, and MCP; drafts must remain absent from every production surface.
