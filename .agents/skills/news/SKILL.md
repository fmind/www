---
name: news
description: Turn pasted links into a www.fmind.dev daily news edition with grounded one-sentence descriptions, then validate and publish it. Use for "add these to today's news" or edits under content/news/.
license: MIT
metadata:
  author: Médéric HURIER (Fmind)
---

# News

Each edition is `content/news/YYYY-MM-DD.txt` (a special edition appends a topic: `2026-04-23-google-next.txt`). The validated editions feed `/news/`, one page per edition, `/news/<slug>.md`, `/news/feed.xml` (one Atom entry per edition), the sitemap, and `llms.txt`. Startup rejects a malformed line, a non-HTTPS link, or a link already published in another edition.

1. Prepare the owner's links: `uv run --locked python -m scripts.news prepare [--date YYYY-MM-DD] URL...`. It strips trackers, normalizes YouTube, X, and arXiv URLs, resolves shorteners, and reports per URL `ok`, `duplicate` (with the edition that has it), `invalid`, or `fetch_error`. Drop duplicates and tell the owner. For a `fetch_error`, find the primary source before writing; never describe a link from its title or URL alone.
1. Write one plain-text line per link: `- Title: https://... - Description`. Keep the source title without site suffixes. The description is one active-voice English sentence that does not repeat the title and leads with the engineering change: mechanism, versions, benchmark numbers, cost or latency, license. Use only facts present in the prepared `title`, `description`, or `excerpt`, or in a primary source you read. No Markdown, links, or emoji inside the line.
1. Order by developer impact: major model releases, agent runtimes, and sandboxes first; then SDKs, CLIs, libraries, and protocols (MCP, A2A); then infrastructure deals, hardware, and ecosystem news; individual posts, podcasts, and consumer apps last. When adding to an existing edition, merge and re-sort it.
1. Validate with `uv run --locked pytest tests/test_news.py`, which loads every published edition. Show the owner the edition and wait for their OK before publishing.
1. Publish: commit only the edition as `feat(news): add YYYY-MM-DD edition` (or `fix(news): ...` for a correction) and push `main`, which deploys production through the normal gate; this needs the owner's deploy authority. Watch `gh run list --workflow deploy.yml --commit <sha>`, then check `https://www.fmind.dev/news/<slug>/` and `/news/feed.xml` live.

A daily edition is content, not a release: no version bump, tag, or changelog entry. Correct a published line in place; removing a link that readers already received in the feed needs the owner's OK.
