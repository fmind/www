+++
title = "Agent Docs: Answer Locally Before the Web — A Shared Reference for Every Coding Agent"
description = "Pair-program with a coding agent for an afternoon and you start noticing a quiet, recurring tax."
date = "2026-05-14"
tags = ["Coding", "Project"]
slug = "agent-docs-answer-locally-before-the-web-a-shared-reference-for-every-coding-agent"
syndicated = "https://medium.com/@fmind/agent-docs-answer-locally-before-the-web-a-shared-reference-for-every-coding-agent-c91e16a8c330"
draft = false
+++

Pair-program with a coding agent for an afternoon and you start noticing a quiet, recurring tax. Every time the agent reaches for a flag, a config field, or a CLI subcommand, it fires off a web search. Then another. Then a third when the second one returned a 2023-era blog post for a tool you upgraded last week.

Each round-trip is a few seconds, a few tokens, and — worse — a chance for the agent to pick a plausible-looking answer from the wrong version of the docs. Multiply that by every session, every contributor, every agent on the team, and the tax is no longer quiet.

I built [**agent-docs**](https://github.com/fmind/agent-docs) to make my agents answer locally before they answer remotely. It is a small set of file-based [Agent Skills](https://agentskills.io/home) that seed, read, and refresh a curated `.agents/docs/` reference for the tools your project actually uses. One install, three commands, three coding agents ([Claude Code](https://code.claude.com/docs/en/overview), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot](https://github.com/features/copilot)) — the same answer for the same question, every run.

![Agent Docs: Project Docs that Answer Locally — https://github.com/fmind/agent-docs](/static/img/articles/agent-docs-answer-locally-before-the-web-a-shared-reference-for-every-coding-agent/cover.webp)

Agent Docs: Project Docs that Answer Locally — [https://github.com/fmind/agent-docs](https://github.com/fmind/agent-docs)

This is the follow-up to my [previous post on supagents](https://fmind.medium.com/supagents-one-source-to-rule-your-coding-subagents-) — same bet on the shared `.agents/` ground, applied to a different layer of the stack.

### The hallucination tax has a quieter cousin

When people talk about LLM failure modes, they usually mean hallucination — confident statements that turn out to be invented. That’s real. But there’s a quieter failure mode I see far more often in practice: **lossy retrieval**.

The agent doesn’t make things up. It does its honest best and lands on the wrong page. A search for “Gemini CLI hooks” returns a blog post that pre-dates the feature. A search for “Cloud Run revisions” returns the 2022 docs, before the rewrite. The agent reads what’s in front of it, summarizes correctly from the source it found, and produces an answer that is technically faithful to a stale or low-quality input.

You don’t catch lossy retrieval by reading the agent’s output. You catch it three turns later, when the implementation doesn’t compile against the current SDK and you trace it back to a flag that was renamed in v0.4.

The fix that occurred to me, after the third time the same agent web-searched the same `gemini settings.json` page, was almost embarrassingly simple: **stop searching for what we already know**. Pin the URLs once. Make every agent on the project read from the same shortlist before it touches the web.

### The Code Wiki nudge

I won’t pretend I came up with the wiki framing in a vacuum. [Code Wiki](https://codewiki.google/) — a recent project out of Google Labs — was the nudge. The pitch resonated immediately: maintain a curated, version-aware knowledge base that a coding agent can query first, instead of asking it to re-discover the same facts every session.

What I wanted, though, was different in three specific ways. I wanted it **local** — committed to the repo, diffable in a PR, not behind a service. I wanted it **scoped to the project** — only the tools and services this codebase actually depends on, nothing else. And I wanted it to work across all coding agents I use daily, not just one.

So agent-docs is my take: a tiny on-disk reference set, owned by the project, read by any agent that respects the [`AGENTS.md`](https://agents.md/) convention.

### What lives in `.agents/docs/`

After you run the gather skill, your project carries a small new directory:

```text
.agents/docs/
├── INDEX.md
├── gemini-cli/
│   ├── DOC.md
│   └── HOOKS.md
└── cloud-run/
    └── DOC.md
```

`INDEX.md` is a one-line-per-topic dispatch table. Each `DOC.md` is the entry point for a topic, and large subsystems can split into sibling files (`HOOKS.md`, `EXTENSIONS.md`) with their own refresh clocks.

The crucial design choice is what each `DOC.md` is — and is not. It is a **navigation map**, not a copy of the docs. Concretely, every `DOC.md` carries:

1. A one-paragraph summary of the topic and where it fits.
2. A terse list of key concepts (settings file, slash commands, hooks, MCP servers).
3. A **documentation map** — the upstream sidebar, captured as one-line link entries grouped by section. Each entry is `[Page title](url)` — short hook on what’s there.
4. An optional Patterns section with paste-ready snippets, capped at five per topic, each tied to an inline \_Source: …\_ link.

The pattern I keep coming back to is: _land the agent on the right upstream URL in one hop, then fetch upstream if it needs depth_. Not every fact gets captured locally — only the navigation, plus a handful of high-frequency snippets when the team decides they’re worth it.

### Three skills, one small loop

The whole thing is three skills. They are deliberately small and they compose into a loop you can reach for without thinking.

![Relationships between Coding Agents, Skills, and Local/Remote Sources](/static/img/articles/agent-docs-answer-locally-before-the-web-a-shared-reference-for-every-coding-agent/02.webp)

Relationships between Coding Agents, Skills, and Local/Remote Sources

### `/gather-agent-docs` — seed the reference

`/gather-agent-docs` inspects your project’s manifests (`package.json`, `pyproject.toml`, `go.mod`, `cloudbuild.yaml`, `apphosting.yaml`, `mise.toml`) and picks three to eight real topics. It does not guess at what the project “might” use; it picks what the project _declares_.

For each topic, it fetches one upstream nav source — the docs sidebar, the README’s docs section, or the sitemap as a fallback — and writes a `DOC.md` with the navigation map mirroring how upstream organizes itself. `INDEX.md` gets one dated line per topic.

The default capture tier is intentionally light: title + URL + one-line hook for every page in the upstream nav. That’s it. Paste-ready snippets are opt-in (`/gather-agent-docs deepen gemini-cli`), capped at five per topic, and only added when the team actually reaches for them often.

### `/use-agent-docs` — read before searching

This is the skill that earns its keep on every run. Before the agent reaches for the web on a topic that’s part of the project, it reads `.agents/docs/INDEX.md`, opens the matching `DOC.md`, scans the documentation map, and fetches the right upstream URL directly.

If the index is missing, it’s a no-op — the agent falls through to normal research. If a captured snippet covers the question, the agent uses it (each one carries its upstream source link, so it can verify). If the answer needs flag-level depth, it goes one hop upstream to a URL it already knows is the canonical one.

Crucially, this is the skill I do not have to remember to invoke. It’s wired as a trigger: “before web-searching for a project topic, check `.agents/docs/`”. Once installed, the agent reaches for it on its own.

### `/refresh-agent-docs` — keep it honest

A curated doc set that is allowed to rot is worse than no doc set, because it lies with confidence. `/refresh-agent-docs` is the gardener.

Every `DOC.md` opens with YAML frontmatter:

```yaml
---
last_verified: 2026-05-08
upstream_commit: 9f3c2b1
sources:
  docs: https://google-gemini.github.io/gemini-cli/
  repo: https://github.com/google-gemini/gemini-cli
  changelog: https://github.com/google-gemini/gemini-cli/releases
---
```

The refresh skill reads that metadata and tries cheap paths first. If `upstream_commit` matches upstream HEAD, the page is verified by definition — bump the date, move on. If the changelog has no entries newer than `last_verified`, same outcome. Only when those short-circuits miss does it fall through to a link-rot scan, then a full re-fetch.

The richer the frontmatter, the more refreshes complete in a single HTTP call. When a page can’t be re-verified this session, the skill stamps a visible `> ⚠ Stale` banner at the top so future agents see the warning before they trust the contents.

This is what I mean by **honest staleness**. The doc set is allowed to age — that’s fine — but the age is always declared, never hidden. The `[YYYY-MM-DD]` next to each topic in `INDEX.md` is the _oldest_ verification date across the topic’s files, so the index shows the staleness floor at a glance.

### A walkthrough on a real project

Here is what a typical session looks like, lightly compressed from a real run on a Cloud Run + Gemini CLI project:

```console
$ /gather-agent-docs
  → inspects manifests, picks: gemini-cli, cloud-run, firebase-app-hosting
  → fetches one upstream nav per topic
  → writes .agents/docs/INDEX.md and 3 DOC.md files
  → "Seeded 3 topics under .agents/docs/. Review the diff before committing."

$ /gather-agent-docs deepen gemini-cli
  → adds up to 5 Patterns snippets to gemini-cli/DOC.md, each with _Source: …_
  → bumps last_verified

# Later, mid-session, the agent is asked to wire up a Gemini CLI hook…
$ "Can you add a pre-tool hook that blocks rm -rf?"
  → /use-agent-docs fires implicitly
  → reads INDEX.md, opens gemini-cli/DOC.md, scans the documentation map
  → finds gemini-cli/HOOKS.md, opens it, picks the snippet for pre-tool hooks
  → writes the hook against the current schema, not a 2024 blog post

# A month later…
$ /refresh-agent-docs gemini-cli
  → smart path: upstream_commit moved; scans changelog since last_verified
  → finds one entry touching hooks; re-fetches HOOKS.md's snippet sources
  → repairs two renamed links in DOC.md's documentation map
  → "gemini-cli: links repaired (DOC.md), snippet edits (HOOKS.md)."
```

The two things I notice consistently after running this for a few weeks:

1. **Round-trips collapse.** The “search → skim → search again” loop turns into a single fetch. The agent’s output shows up faster because there’s less network in front of it.
2. **Answers stop drifting between sessions.** Three contributors asking the agent “where is X configured?” get the same upstream page, because the agent reads the same map.

### Local-first, on purpose

A few people asked me, when I described this, why I didn’t just point the agent at the upstream docs site directly and let it search. Two reasons.

First, _scope_. The upstream docs for any non-trivial tool are an ocean. The right answer for a given project is a narrow shoreline — the flags this team uses, the patterns this codebase follows, the canonical URL we trust. Curating the map shrinks the search space from “every page on the site” to “the dozen pages we actually touch”.

Second, _commit-ability_. `.agents/docs/` lives in git. It travels with the code. It diffs in PRs. When a contributor updates the Gemini CLI version, the PR can include the refreshed map alongside the version bump, reviewed in the same place. A hosted service can’t be diffed in your PR.

There is a real cost: someone on the team has to run `/refresh-agent-docs` periodically, and someone has to decide when a snippet is worth capturing. That cost is the point. It is the same cost we pay to maintain a `README.md` that doesn’t lie — and we pay it because the alternative is worse.

### Where this sits in the `.agents/` stack

If you read my [supagents post](https://fmind.medium.com/supagents-one-source-to-rule-your-coding-subagents-), the framing here will feel familiar. I keep finding the same pattern: a thing that should be one source, fragmented across N coding-agent harnesses, that we can unify in the shared `.agents/` ground.

Supagents handles **subagent personas** — one markdown source compiled to `.claude/agents/`, `.gemini/agents/`, .github/agents/. Agent Docs handles **project knowledge** — one `.agents/docs/` folder, read by any agent that follows the [AGENTS.md convention](https://agents.md/) (which now includes Claude Code, Gemini CLI, and GitHub Copilot).

These are two slices of the same bet: the future of coding agents is not a winner-takes-all framework. It’s a shared file-system layout, with small composable conventions, that every tool reads in its own way. The friction goes away when we stop reinventing storage formats and start respecting a common root.

### Install and try it

The three install paths mirror the three coding agents:

```text
# Claude Code
/plugin marketplace add fmind/agent-docs
/plugin install agent-docs@agent-docs

# Gemini CLI
gemini extensions install fmind/agent-docs

# GitHub Copilot (CLI)
copilot plugin marketplace add fmind/agent-docs
copilot plugin install agent-docs@agent-docs
```

Then, inside a project:

```text
/gather-agent-docs        # seed .agents/docs/
/use-agent-docs           # fires implicitly on web-search triggers
/refresh-agent-docs       # run periodically -- once a sprint is enough
```

The repository is at [github.com/fmind/agent-docs](https://github.com/fmind/agent-docs). The [`examples/`](https://github.com/fmind/agent-docs/tree/main/examples) directory ships a worked sample of what gather produces — two topics, one with a subtopic split — so you can see the output shape before you run it.

### Small tools, on purpose

I keep coming back to the [Linux philosophy](https://fmind.medium.com/ai-agents-as-an-operating-system-rediscovering-the-linux-philosophy-f0e76f29ebdb) when I build things in this space: small tools, one job, composable. Agent Docs is three skills (gather, use, refresh) that touch one folder (`.agents/docs/`) and respect one shared root (`.agents/`). That’s the whole surface area.

The bet is that this is enough. A curated map is cheaper than a clever retrieval system, the same way a README.md is cheaper than an auto-generated wiki. The reason README.md survived every documentation-platform fad for two decades is that it’s a flat file that travels with the code and reads correctly without a runtime. .agents/docs/ is the same shape, aimed at the agent instead of the human.

If you are running coding agents on a real project — and tired of watching them re-search the same SDK every afternoon — give it a try. If it saves you the third web round-trip on a Friday, it has earned its keep.
