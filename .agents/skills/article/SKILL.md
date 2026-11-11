---
name: article
description: Publish, revise, or retire www.fmind.dev articles under content/articles/.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Articles

`content/articles/<slug>.md` is authoritative; revise or retire published articles only with owner authorization. New articles flow from `fmind/pub` (`pub publish` exports body, cover, and figures, runs `build:images`, and merges the PR). After editing `content.py` or `scripts/build_images.py`, run `SITE_REPOSITORY=$PWD mise -C ~/fmind/pub run check:site-contract` or update `pub` in step.

1. **Validate frontmatter**: match filename and `slug`, require typed dates and `draft`, and reject unknown keys (including retired `canonical` and `syndicated`). Start the body with the cover image and descriptive alt text (reused for social cards and JSON-LD captions).
1. **Check tags and code fences**: use unique tags from `src/www/tags.py` (new tags need a matching CSS rule and ≥1 article) and language-tagged code fences.
1. **Build and verify media**: keep source images near 2.4MP, upright without EXIF rotation, with case-insensitively unique stems per folder (`<stem>-<width>.webp`). Covers are static `cover.{webp,gif,png,jpg,jpeg}`; other animated sources are ≤800px wide. Body images and MP4s live under `/static/img/articles/` with non-empty alt text. Run `mise run build:images` and commit derivatives plus `assets/image-derivatives.json` (`check:images` verifies hashes and recipes read-only).
1. **Inspect layout and diagrams**: check desktop and mobile; figures must fit the 1280px column without horizontal scroll, with diagram labels ≥12px and height ≤1300px (fix unreadable diagrams at source).
1. **Run gates**: pass `mise run all` and `mise run check:links` (only legitimate exceptions in `typos.toml`). Follow [release](../release/SKILL.md) when authorized.

`src/www/content.py` disables raw HTML, normalizes section anchors, folds a following paragraph into `<figcaption>` only when it matches image alt text, keeps `FIGURE_SIZES` aligned with CSS, and exposes H2 rail navigation at ≥1920px when ≥2 H2s exist (verify long labels and no-JS links).
