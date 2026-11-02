+++
title = "Agent Levers: A Plan-Do-Check-Act Loop That Makes Coding Agents Finish What They Start"
description = "A coding agent is only as useful as the spec you give it. That sentence sounds like a truism until you watch it play out for an afternoon."
date = "2026-05-25"
tags = ["Coding", "Guide"]
slug = "agent-levers-a-plan-do-check-act-loop-that-makes-coding-agents-finish-what-they-start"
draft = false
+++

A coding agent is only as useful as the spec you give it. That sentence sounds like a truism until you watch it play out for an afternoon.

Type too little — “add password sign-in” — and the agent improvises. It picks a JWT library you don’t use, skips rate-limiting, ships a flow that works on the happy path and fails the moment you blow on it. Type too much — every constraint, every test name, every file path — and you’ve done the agent’s homework. You are the bottleneck, not the multiplier.

I have been trying to find the shape of the work _between_ those two extremes for months. I built [**agent-levers**](https://github.com/fmind/agent-levers) — a small set of [Agent Skills](https://github.com/anthropics/skills) that give the agent a structured **plan → do → check → act** loop on disk — to do the structuring work I kept doing by hand.

This is the third post in a thread about the shared `.agents/` ground, after [supagents](https://www.fmind.dev/articles/supagents-one-source-to-rule-your-coding-subagents/) (one subagent source, many targets) and [agent-docs](https://www.fmind.dev/articles/agent-docs-answer-locally-before-the-web-a-shared-reference-for-every-coding-agent/) (a curated, local doc reference). Same bet, different layer: this one is about the **workflow** an agent runs _inside_ a non-trivial task.

![Agent Lever: Multiply the agent’s force, divide the human’s effort — https://github.com/fmind/agent-levers](/static/img/articles/agent-levers-a-plan-do-check-act-loop-that-makes-coding-agents-finish-what-they-start/cover.webp)

Agent Lever: Multiply the agent’s force, divide the human’s effort — [https://github.com/fmind/agent-levers](https://github.com/fmind/agent-levers)

### The two failure modes of unguided agents

After enough sessions, I started noticing the same two failure patterns, no matter which coding agent I drove.

**The agent claims success it didn’t verify.** It says “I implemented the rate limiter,” shows a diff, and moves on. You ask “did the test pass?” and discover it never ran, or it ran in an ad-hoc shell, or — the meanest version — it passed in the agent’s session and fails the moment you re-run it from a clean terminal. The status report isn’t lying. It’s just not grounded in a verifier.

**The agent runs away.** The first test fails. The second attempt fails. The third attempt fails. Forty minutes later, the diff is twice as large as the original task, and nothing is green. There is no internal “I should stop and ask” trigger because the agent is doing what it was told: keep trying until the test passes.

Both failure modes have the same root cause: the loop is _implicit_. The agent makes up the loop on the fly. Each session improvises a new plan, a new sense of done, a new sense of when to give up.

The fix I kept reaching for, before I built this, was structure I imposed by hand: a numbered checklist in the prompt, an explicit “run this command after each change,” a polite “stop and ask if you’ve failed three times in a row.” It worked. It also lasted exactly one session, because the next task started from a blank prompt.

Agent Levers is that structure, externalized. Once.

### The lever metaphor

The name is the bet. A lever multiplies force on one end while reducing effort on the other. The human pushes on the short side — a one-line brief, plus answers to a handful of clarifying questions — and the agent lifts the long side: investigation, planning, execution, verification, learning.

The shape of the work is the [Deming cycle](https://en.wikipedia.org/wiki/PDCA), borrowed from process engineering and applied to a different kind of factory: **plan → do → check → act**. Every non-trivial coding task already follows that shape; it just usually lives in the agent’s head, where you can’t audit it. The point of the framework is to push the loop onto disk, where each step is an artifact that can be reviewed, paused, resumed, and continued by a different session.

![Relationship between Coding Agents and Agent Levers](/static/img/articles/agent-levers-a-plan-do-check-act-loop-that-makes-coding-agents-finish-what-they-start/02.webp)

Relationship between Coding Agents and Agent Levers

### Four commands, one folder

The whole surface area is four slash commands, three of them user-facing and one of them an internal dispatcher you mostly forget exists.

- `/lever-init` — bootstraps the framework on a fresh repo.
- `/lever-new <title>` — captures intent. The first turn is _chat-only_ — clarifying questions, proposed enhancements, a draft brief inline. No files land until you agree.
- `/lever <id>` — runs the chain. Plan → do → check → act, autonomously until a pause or a terminal state.
- `/lever-status [<id>]` — read-only inspector; lists levers, shows one in detail, or cancels one.

Everything else lives in two files, per lever, on disk: a `lever.yaml` that holds the machine state, and a `LEVER.md` that opens with a TL;DR and grows narrative sections as each step runs. Half a day of agent work, audited in twenty lines.

### The two-session split

The thing I keep coming back to is the deliberate split between `/lever-new` and /lever.

`/lever-new` is high-context: you and the agent in chat, narrowing down what you actually want. The agent reads project conventions, asks clarifying questions, proposes enhancements you didn’t ask for but probably want (“you specified Google OAuth — want GitHub too?”), drafts the brief inline. No files land until you say “looks good.”

`/lever` is mechanical: a fresh session, reading the state, executing the matching step, advancing the pointer. The dispatcher loads only the step it needs — never all four at once. The agent’s context stays clean across the chain.

The two-session split has a property I value enough to call out: **brief-time is the only place the human is in the loop**. Once you run `/lever 1`, the chain runs to completion (or to a structural pause) without re-asking what you wanted. If the brief was crisp, you don’t see the chain again until there is a diff to review.

I cannot overstate how much I prefer this to the “agent asks twenty questions while implementing” rhythm. The cost of a sharp brief is paid once, up front, in the cheapest part of the process. Everything after compounds on that investment.

### The four steps, briefly

**Plan** reads the brief, investigates the codebase and external docs itself — `grep`, reading tests, pinning dependency versions, fetching authoritative docs — and writes a small set of _acceptance criteria_, each paired with a typed verifier (a shell command, a screenshot to confirm, or a manual rubric). It also sets a budget — iterations, minutes, failed-streak — so the next step has an explicit leash.

The hard rule on verifiers is: **test the behavior, not the agent’s past actions**. A criterion that says “function `loginHandler` exists in `src/routes/auth.ts`” is bookkeeping — the agent can satisfy it by writing the function and then grepping its own diff. A criterion that says `POST /auth/login` returns a JWT on valid credentials is verification — it passes when the handler _works_.

**Do** drives the criteria one at a time. It picks the first failing one, makes the smallest change that should flip it (TDD-style by default for shell verifiers), runs the verifier, and logs the result. Out-of-scope ideas get parked, not silently bundled into the diff. When the budget runs out, the loop stops with state on disk — raise the cap, narrow scope, or hand off; prior passes stay green.

**Check** is the step that earns the framework its keep. It re-runs every verifier from a _fresh shell_ — not the agent’s session — to catch criteria that secretly relied on cached state. Then it does something I have not seen anywhere else: a **chain audit**. It walks the trail from brief to plan to events to diff, asking at each handoff whether the next step honored the previous one. The silent-killer audit is the last hop — does the diff actually deliver what the brief asked for, or did the agent build something adjacent? Tests can pass while intent quietly drifts; the chain audit is what catches that.

**Act** runs only if check surfaced _hints_ — moments where a decision deserved more guidance, or where a recurring pattern started to show. It picks the right surface for each: a project rule lands in `AGENTS.md`, a skill flaw lands in the skill, work that isn’t a rule becomes a follow-up /lever-new. The edits arrive as proposals in the working tree, reviewed in the same PR as the implementation. **The next lever inherits the rule, not the mistake.**

This last property is the one I find most underappreciated: the framework has a built-in mechanism for the agent’s workflow to improve. A gotcha that surfaces three times in three separate levers earns its way into `AGENTS.md` by being staged three times. You don’t have to remember to tell the agent about it next session.

### A walkthrough on a real task

Two human inputs, two sessions, one finished feature.

```console
$ /lever-new add password sign-in
  → first turn: chat-only — clarifying questions, proposed enhancements, draft brief
  → "rate-limit policy for /auth/login? OAuth uses 5/min/IP — match it?"
  → "looks good"
  → captures the brief on disk
  → "Brief captured. In a new session, run /lever 1 to start the chain."

# Fresh session, hours or days later.
$ /lever 1
  → plan:  investigates the auth + middleware code, writes 4 criteria with shell verifiers
  → do:    C1 pass · C2 pass · C3 fail (limiter not wired) · C3 pass · C4 pass
  → check: rerun from fresh shell — all green
           chain audit: Brief→Plan · Plan→Do · Do→Result · Result→Intent — all pass
           2 hints surfaced
  → act:   hint 1 → AGENTS.md +5/-0 (explicit "attach middleware" sub-step in TDD)
           hint 2 → recommend /lever-new enforce_route_middleware_lint
  → "Ran: plan → do → check → act. 4/4 passed. 2 hints landed. Done — diff is staged."
```

The interesting moment is the limiter miss at C3 — the kind of off-by-one that on a normal “agent, implement this” run becomes a Slack thread two days later, when QA notices the rate limit doesn’t fire. Here, it surfaces as a single fail row, recovered in the next iteration, lifted into a hint by check, and codified as a rule by act.

That is the whole pitch in one trace: the loop catches its own mistakes before the human sees them, and the lessons compound for next time.

### Install and try it

The three install paths mirror the three coding agents:

```text
# Claude Code
/plugin marketplace add fmind/agent-levers
/plugin install agent-levers@agent-levers

# Gemini CLI
gemini extensions install fmind/agent-levers

# GitHub Copilot (CLI)
copilot plugin marketplace add fmind/agent-levers
copilot plugin install agent-levers@agent-levers
```

Then, inside a project:

```text
/lever-init                       # bootstrap the framework
/lever-new <title>                # capture a new task (Session 1)
/lever <id>                       # run the chain (Session 2)
/lever-status [<id>]              # inspect or cancel
```

The repository is at [github.com/fmind/agent-levers](https://github.com/fmind/agent-levers). The [`examples/levers/`](https://github.com/fmind/agent-levers/tree/main/examples/levers) directory ships two worked walkthroughs — a happy path and a scenario where check routes back to do — so you can see what the artifacts look like before you run anything.

### The lever effect

A real lever’s mechanical advantage is a ratio: force out per unit of effort in. For a coding agent, the equivalent is **verified, intent-aligned work shipped per minute of human attention spent**. Clear briefs, typed verifiers, bounded loops, on-disk state, lessons that compound — each one bends that ratio in the same direction.

We are not trying to build an agent that needs us less. We are building the fulcrum that lets the same hour of human attention move more. Give [**agent-levers**](https://github.com/fmind/agent-levers) a try — the lever is real when you can feel the asymmetry.
