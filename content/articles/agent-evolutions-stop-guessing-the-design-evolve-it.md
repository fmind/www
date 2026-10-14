+++
title = "Agent Evolutions: Stop Guessing the Design — Evolve It"
description = "Most coding-agent tasks have one right answer hiding behind a workflow."
date = "2026-06-01"
tags = ["Coding", "Project"]
slug = "agent-evolutions-stop-guessing-the-design-evolve-it"
syndicated = "https://medium.com/@fmind/agent-evolutions-stop-guessing-the-design-evolve-it-5074a41b99d3"
draft = false
+++

Most coding-agent tasks have one right answer hiding behind a workflow. “Add password sign-in.” “Fix the off-by-one in the pagination cursor.” “Refactor this handler to use the new client.” The job is to converge — pick the path, drive it to done, ship the diff. That is the world [**agent-levers**](https://fmind.medium.com/agent-levers-a-plan-do-check-act-loop-that-makes-coding-agents-finish-what-they-start) lives in.

Some tasks aren’t shaped like that. “Which prompt wins?” “Which caching strategy is fastest?” “Which library shape is friendlier to call from a worker?” There is no single correct path. There are five plausible ones, the differences are not obvious from inspection, and the only honest way to pick is to _measure_. The shape of the work is **divergent** — branch out, evaluate, keep what works.

I kept reaching for that second shape and finding nothing on the shelf. So I built [**agent-evolutions**](https://github.com/fmind/agent-evolutions) — a small set of [Agent Skills](https://github.com/anthropics/skills) that turn a coding agent into a budgeted genetic search over a design space, with verifiable scoring at every step.

This is the fourth post in a thread on the shared `.agents/` ground, after [supagents](https://fmind.medium.com/supagents-one-source-to-rule-your-coding-subagents-), [agent-docs](https://fmind.medium.com/agent-docs-answer-locally-before-the-web), and [agent-levers](https://fmind.medium.com/agent-levers-a-plan-do-check-act-loop-that-makes-coding-agents-finish-what-they-start). Same bet, different question: levers ask _“did we build it right?”_, evolutions ask _“did we pick the right thing to build?”_

![Agent Evolutions: Genetic exploration of solution spaces, with verifiable scoring — https://github.com/fmind/agent-evolutions](/static/img/articles/agent-evolutions-stop-guessing-the-design-evolve-it/cover.webp)

Agent Evolutions: *Genetic exploration of solution spaces, with verifiable scoring — *[https://github.com/fmind/agent-evolutions](https://github.com/fmind/agent-evolutions)

### The design-by-intuition tax

Three failure modes I keep watching teams pay for — including my own:

**The five-minute eyeball test.** Two prompts on the screen, both look reasonable. One person prefers the terser one; another prefers the structured one. The team picks whichever was authored by the loudest reviewer. Three weeks later a quiet regression appears on a slice of traffic nobody A/B’d against.

**Taste vs. taste.** “Which client shape should we expose — fluent builder or plain options bag?” Six people, six opinions, zero numbers. The argument lasts a week. Whatever ships is then defended for years because rolling it back is more expensive than living with it.

**The benchmark that becomes a vote.** “Which caching strategy is fastest?” Real, mechanical, measurable. Then someone runs _one_ manual test, on _one_ workload, and reports a winner. Nobody asks how sensitive the result is, nobody runs the loser to confirm, nobody bothers with a second seed.

These all share a common shape: a design question with multiple plausible answers and at least one mechanical measure — _and we answered it with intuition anyway_. The cost of guessing wrong is rarely visible at decision time. It shows up months later as a refactor.

What I wanted was a tool that made the right move — _generate variants, measure, evolve, pick_ — cheaper than the wrong move. That is the gap agent-evolutions is aimed at.

### Convergent and divergent loops, side by side

The clearest way I can frame the relationship to agent-levers is by the shape of the loop.

Levers is **convergent**. One workspace, one diff, one verifier set, plan → do → check → act in a sequential chain. The question being answered is _how do we drive this single task to done_. The whole machine is tuned to finish.

Evolutions is **divergent, then convergent**. N parallel workspaces (one per variant), N independent results, batched generations that learn from the previous batch, a final pick at the end. The question is _which of several plausible designs measures best_. The machine is tuned to explore first, then collapse.

Both loops live on the same `.agents/` ground, both use file-based state, both let any compliant coding agent drive them. They are not competitors — they are complementary tools for different question shapes. Most non-trivial work, in my experience, is mostly levers and occasionally evolutions. The trick is knowing which kind of question you’re holding.

### Genetic search, not random sampling

The first thing people picture when I say “spawn variants in parallel and pick the best” is brute-force Best-of-N: fan out thirty prompt mutations, score them, keep the top one. That is sampling. It is blind, and it scales badly — doubling the budget barely improves the answer because every sample is drawn from the same flat distribution.

Agent-evolutions runs a **genetic** loop instead:

- **Generation 1** seeds a small, _diverse_ set of hypotheses — qualitatively different approaches, not minor variants of one idea.
- **Generation 2+** mutates the top survivors, crosses pairs over, and injects a small share of fresh exploration variants to avoid premature collapse.
- **Batches are sized to `budget.parallel`**, deliberately, so the loop can _learn between batches_ instead of fanning out blindly.
- **Stopping** is automatic: budget cap, wall clock, score plateau across N generations, or no survivors.

Each generation conditions on what worked in the previous one. That is the qualitative difference — and the reason a small directed search routinely beats a much larger random one. The skill’s documented `optimize cli startup` walkthrough finishes in 24 evaluated variants across 4 generations, with the winner from generation 2 — not generation 1.

### Three commands, three phases

The whole surface area is three slash commands, one per phase:

- **Capture** — /new-agent-evolution \<title\> discusses the brief (objective, gates, rubric, scope, budget) and commits it when you agree.
- **Run** — /run-agent-evolution \<id\> plans a batch, spawns variants in parallel, ingests each `result.json`, scores, evolves, and stops on a condition.
- **Apply** — /apply-agent-evolution \<id\> diffs the winner workspace against the live repo, confirms with you, copies it in, and optionally re-runs gates against the repo.

Diff winner workspace vs the live repo → confirm → copy in → optionally re-run gates against the repo.

The state machine is the one design choice I find myself most pleased with. There is no step counter, no pause flag, no “current phase” field. Phase is **derived from the presence of fields** in `evolution.yaml`:

- empty `variants` → **ready** to run
- has `variants`, no `winner` → **running**
- has `winner`, no `applied` → **evaluated**
- has `applied` → **done**

Each skill reads the yaml on entry, infers what phase the evolution is in, and refuses to run outside its own. Capture won’t recreate a brief that already exists. Run won’t re-rank a finished evolution. Apply won’t run without a winner. The skills are stateless; the disk is the source of truth. Crash mid-batch, restart, and the next invocation picks up exactly where the files left off.

### The contracts that make the scoring honest

A genetic loop with sloppy scoring is just an expensive random walk. Agent-evolutions leans hard on three contracts that keep selection grounded.

**Gates are binary.** Each gate is a shell command. Exit 0 means pass, anything else means fail. A variant that fails any gate is _excluded from ranking entirely_ — no partial credit, no negotiation. Gates are how the framework refuses to compare “fast but broken” against “correct and slow”.

**The rubric is numeric.** Each rubric axis has a `direction` (minimize or maximize) and a weight. The composite score is a rank-normalized weighted mean across axes — robust to outliers, well-defined under partial data, and crucially **recomputed on read by the run skill, never persisted** in the yaml. The yaml stores raw rubric values; the leaderboard view derives from them. You cannot accidentally enshrine a stale score because there is no stored score to enshrine.

**Criteria are frozen up front.** This is the load-bearing rule. Gates and rubric axes are agreed during the Capture phase and then locked. The run skill refuses to add a new rubric axis after results come in. Without that rule, the evaluator silently turns into a rationalization engine — adding the axis on which the variant the agent likes anyway happens to win.

The unstated cousin of these contracts: no silent retries, no narrative scoring. A failing gate stays failed. A missing measurement is missing, not interpolated. The leaderboard is allowed to be ugly.

### The file-based sub-agent contract

Each variant runs as its own sub-agent, in its own workspace (a `git worktree` by default), starting from HEAD. The contract between the parent and each child is not chat — it is a file.

![Relationship between Agent Evolutions Concepts](/static/img/articles/agent-evolutions-stop-guessing-the-design-evolve-it/02.webp)

Relationship between Agent Evolutions Concepts

Every variant sub-agent writes variants/v\<n\>/result.json, validated against a [JSON Schema](https://github.com/fmind/agent-evolutions/blob/main/result.schema.json). The parent reads files, not chat output. Four properties fall out of that decision:

1. **Crash-survivable.** A child that finishes its work before the parent gets a chance to read its reply still leaves its result on disk. Partial batches don’t disappear.
2. **Audit trail.** Every variant’s exact result lives in git. You can re-rank a historical evolution from its files alone, weeks later.
3. **No JSON-in-chat parsing.** The classic failure mode where a sub-agent’s reply is “JSON-ish” — with a friendly paragraph in front, or three backticks, or a stray comma — never enters the pipeline. The schema validates a file.
4. **Parallelism stays clean.** Six sub-agents writing to six different files do not pollute one shared transcript. No interleaved thinking, no merge step.

I would not bother spelling this out if I had not lost an afternoon, more than once, to the JSON-in-chat trap on a previous prototype. File-based sub-agent I/O is the kind of detail that looks pedantic on slide one and saves the whole loop by slide four.

### A walkthrough — optimize cli startup

The shipped example trims a Node.js CLI’s cold-start time on — version. The brief pins one gate set (build green, tests green) and one rubric axis (median of five hyperfine runs, minimize).

```console
$ /new-agent-evolution "optimize cli startup"
  → discusses objective, gates, rubric, scope, budget
  → on "looks good", commits .agents/evolutions/1-optimize_cli_startup/

$ /run-agent-evolution 1
  → gen 1: seeds 6 diverse hypotheses — lazy-load, build-time inline,
           plugin-registry map, polyfill strip, prebundled arg-parser,
           dotenv short-circuit
  → spawns 6 sub-agents in parallel; each materializes a worktree,
           implements its variant, runs gates, writes result.json
  → ranks:  v2 (build-time inline) → 142.0 ms · v1 (lazy-load) → 184.2 ms
           v4 fails G2 (test regression) → excluded
  → gen 2: mutates v2 → v7 (v2 + tree-shake help chunk),
           mutates v1 → v8, crosses v2×v3, adds 1 explore
  → ...
  → plateau at gen 4 — top score unchanged across 2 generations
  → stops at 24/30 evaluated; winner v7 at 98.6 ms

$ /apply-agent-evolution 1
  → diffs variants/v7/workspace vs live src/, tsdown.config.ts, package.json
  → "Confirm to apply, or reply abort"
  → "looks good"
  → copies files in; re-runs G1 + G2 against the live repo; both green
```

The moment I find the most instructive is the winner. v7 came from generation 2 — it is _v2 plus a tree-shake tweak that only made sense once v2 had won the first round_. Nobody on the team would have written v7 from scratch in generation 1. Evolution found it because the loop conditioned on v2’s win before composing the next batch. That is the entire pitch of genetic search over sampling, in one trace.

### Where this skill set should not run

Three patterns where I deliberately do not reach for evolutions, and the skill refuses to seed a brief when it spots them:

- **The task is a one-line bug fix, rename, or doc edit.** Just do it. The overhead of a genetic loop is paid in seconds; the task is paid in seconds. The ratio is wrong.
- **There is no mechanical measure — not even a proxy.** “Make this prose more engaging” has no shell exit and no number. Use a normal review.
- **The user has already decided the design.** “Implement X.” is a levers job, not an evolutions job. Don’t manufacture a search space just to use the tool.

If a brief tries to start without a gate or a rubric axis, the Capture skill pushes back: _“we need at least one mechanical check before variants make sense.”_ Either we co-author one, or the evolution doesn’t get a folder. That refusal is on purpose — it is the load-bearing reason variants ranking _means_ something at the end.

### The leverage axis

Agent-levers makes one hour of human attention move more — clearer briefs, typed verifiers, lessons that compound, the same fulcrum logic [I wrote about before](https://fmind.medium.com/agent-levers-a-plan-do-check-act-loop-that-makes-coding-agents-finish-what-they-start). The asymmetry is _human effort in, shipped work out_.

Agent-evolutions sits on a different axis. The input is not human attention, it is _compute_: six or twelve or twenty-four sub-agents running in parallel, each spending tokens on a variant of the same design question. The output is a defensible answer to _which design to ship_. The fulcrum is the same shape — small effort on one end multiplies into directed work on the other — but the lever is bolted to a different wall.

Most teams, today, are spending compute the way a 1990s team spent CPU time on a build: cautiously, one job at a time. The price has dropped, the parallelism has arrived, and the workflows have not caught up. Genetic search on coding tasks is one of the places that gap is widest.

The practical nudge I’ll leave you with: next time a _which design wins?_ thread starts on Slack, count the design points raised against the design points measured. If the ratio is wildly skewed toward opinion — and it usually is — that is the shape of a question agent-evolutions was built to swallow.

### The three install paths mirror the three coding agents:

```text
# Claude Code
/plugin marketplace add fmind/agent-evolutions
/plugin install agent-evolutions@agent-evolutions

# Gemini CLI
gemini extensions install fmind/agent-evolutions

# Antigravity CLI
agy plugin install https://github.com/fmind/agent-evolutions

# GitHub Copilot
copilot plugin marketplace add fmind/agent-evolutions
copilot plugin install agent-evolutions@agent-evolutions
```

To run these skills in [OpenCode](https://opencode.ai/), place or clone the skill directories under `.agents/skills/` (for project scope) or `~/.agents/skills/` (for global scope).

Then, inside a project:

```text
/new-agent-evolution <title>      # capture the brief (Session 1)
/run-agent-evolution <id>         # drive the genetic loop (Session 2)
/apply-agent-evolution <id>       # land the winner (Session 3)
```

The repository is at [github.com/fmind/agent-evolutions](https://github.com/fmind/agent-evolutions). The [`examples/evolutions/`](https://github.com/fmind/agent-evolutions/tree/main/examples/evolutions) directory ships the full `optimize cli startup` walkthrough — brief, variants, scored leaderboard, applied diff — so you can read what the artifacts look like before running anything yourself.

Pick a real question. Give it gates and a rubric. Let the loop run while you make coffee. The answer it comes back with will not be the one you would have written on a whiteboard — and that, more often than not, is the point.
