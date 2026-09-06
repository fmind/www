---
name: article
description: Publish, revise, or retire a www.fmind.dev article with strict metadata, media, and owner gates. Use for authorized changes under content/articles/.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# Publish an Article

Change one article without weakening the immutable-source, validation, media, or owner-publication boundaries.

Published bodies are immutable unless the owner explicitly authorizes a revision or retirement. Local green checks establish readiness, never authority to commit, push, release, deploy, publish, or remove a live page.

## Workflow

1. Add or update articles in `content/articles/<slug>.md` only with explicit publication authority. Write strict TOML frontmatter and apply the roughly 2.4MP body-image budget. This repository owns the published body.
1. Validate metadata in `content/articles/<slug>.md`: filename and `slug` match; required fields, dates, HTTPS provenance, and `draft` are well typed; site-owned articles omit `canonical` and use `syndicated` for external copies.
1. Check tags against `src/www/tags.py`. A new tag requires one `Tag` entry, a matching `[data-tag='…']` rule in `assets/css/input.css`, and at least one article use. Vocabulary construction rejects blank or untrimmed names and descriptions, and duplicate names. Article parsing rejects unknown tags; tests require every vocabulary tag to be used and styled.
1. Generate and review committed media artifacts:

   ```bash
   mise run build:images
   ```

   Commit the updated derivatives and `assets/image-derivatives.json`. Widths live in `src/www/models.py:DERIVATIVE_WIDTHS`; the lock binds exact source and target hashes to the pinned Pillow/WebP recipe. The read-only `check:images` task inside `check` rejects missing, tampered, or recipe-stale rungs.

1. Run local gates:

   ```bash
   mise run format
   mise run check
   mise run test
   mise run test:browser
   ```

   Add legitimate spelling exceptions to `typos.toml`; never weaken or skip the check.

1. Check outbound links before release. This network-dependent gate is separate from `check`:

   ```bash
   mise run check:links
   ```

1. Hand the reviewed change to the `release` skill only when the owner explicitly authorizes publication.

## Gotchas

- `src/www/content.py` parses Markdown with raw HTML disabled, normalizes headings, enhances media, and folds captions. Most source errors surface while `src/www/app.py` constructs immutable state.
- Fence every code block with a language. `src/www/highlighting.py` owns Pygments highlighting, language fallback, and the generated code stylesheet.
- A standalone image becomes a linked `<figure>` bounded by `FIGURE_SIZES`; keep that value aligned with `.article-page` rules in `assets/css/input.css`.
- Fold a following paragraph into `<figcaption>` only when its text repeats the image alt. Compare text, not rendered markup; opening prose is not a caption merely because it follows the cover.
- Fix unreadable diagrams at their source and re-import them. The site acceptance bar is apparent labels of at least about 12px and height of at most about 1300px when fitted to 1280px.
- `src/www/images.py` uses the locked Pillow/WebP recipe and never upscales ordinary rungs. `build:images` reconciles reviewed artifacts; `check:images` verifies them without writing.
- Drafts must remain absent from every production HTML, Atom, sitemap, LLM text, JSON, search, and MCP surface.

## Official Skills

- Use [technical-publishing](~/.agents/skills/technical-publishing/SKILL.md) for the cross-repository editorial and canonical-site handoff.
- Use [playwright](~/.agents/skills/playwright/SKILL.md) for browser regression diagnosis.

## Documentation

- [markdown-it-py](https://markdown-it-py.readthedocs.io/)
- [Pillow](https://pillow.readthedocs.io/)
- [Pygments](https://pygments.org/docs/)
