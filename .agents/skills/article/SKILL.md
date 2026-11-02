---
name: article
description: Publish, revise, or retire a www.fmind.dev article with strict metadata, media, and owner gates. Use for authorized changes under content/articles/.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Articles

The current `content/articles/<slug>.md` is the authoritative body. Revise or retire published content only within owner authorization; publication is separate from local editing.

New articles arrive from the private `fmind/pub` workspace: `pub publish` exports the body, cover, and figures, runs `build:images`, then opens and merges the pull request. pub's pre-push hook and `pub publish` check that export against `../www`; after changing `content.py` or `images.py`, run `SITE_REPOSITORY=$PWD mise -C ~/fmind/pub run check:site-contract` (read-only) or update pub in step.

1. Validate strict TOML frontmatter: matching filename/slug, required fields, typed dates and `draft`. Unknown keys, including the retired `canonical` and `syndicated`, fail validation: every article is published here first.
1. Use unique tags from `src/www/tags.py`. A new tag needs a matching CSS rule and at least one article use. Fence code with a language.
1. Keep source images near the 2.4MP budget, upright without an EXIF rotation tag, and with a stem unique per folder ignoring case (derivatives are `<stem>-<width>.webp`). The cover is `cover.{webp,gif,png,jpg,jpeg}` and never animated; other animated sources must be at most 800px wide. Body images and MP4 videos must be files under `/static/img/articles/` with non-empty alt text. Run `mise run build:images`, review the result, and commit derivatives plus `assets/image-derivatives.json`; `check:images` verifies their hashes and encoder recipe without writing.
1. Inspect desktop/mobile rendering. Figures fit the 1280px column without horizontal panning; diagrams need apparent labels around 12px or larger and height around 1300px or less at that width. Fix unreadable diagrams at their source.
1. Run `mise run all` and `mise run check:links`; add only legitimate spelling exceptions to `typos.toml`. Use the [release skill](../release/SKILL.md) when publication is authorized.

`src/www/content.py` disables raw HTML, normalizes headings into stable section anchors, and folds a following paragraph into a caption only when its text repeats the image alt. Keep `FIGURE_SIZES` aligned with article CSS. Articles with at least two H2 sections expose navigation at widths of 1920px and above; check long labels and no-JavaScript links after heading edits. Feed discovery remains site-wide. The validated collection feeds HTML, Atom, sitemap, LLM text, JSON, search, and MCP; drafts must remain absent from every production surface.
