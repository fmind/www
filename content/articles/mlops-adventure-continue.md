+++
title = "The MLOps Adventure Continues: An AGENTS.md Ready Stack for AI/ML"
description = "AI coding agents amplify repository friction. How we redesigned an MLOps codebase around deterministic single-command gates, SQLite isolation, and AGENTS.md."
date = "2026-08-11"
tags = ["Coding", "MLOps", "Guide"]
slug = "mlops-adventure-continue"
draft = false
+++

![A developer and a robot reading instructions together beside conveyor belts that move packages through a checked gate](/static/img/articles/mlops-adventure-continue/cover.webp)

AI coding agents are the first contributors that read your entire repository and run shell commands non-interactively on day one. But agents also act as friction multipliers. Hand an agent a fragmented toolchain, duplicated CI scripts, or unverified instructions, and it will confidently burn execution loops navigating the disagreement. Hand it a single deterministic gate and machine-readable rules, and its first attempt lands close to green.

Good repository tooling is no longer just developer ergonomics — it is the engineering boundary that makes autonomous AI coding safe.

Over the past two releases of the four repositories behind the [MLOps Coding Course](https://mlops-coding-course.fmind.dev), we refactored our entire developer loop specifically for AI-agent readiness. The headline result was a net deletion: over 900 lines of configuration and glue code removed while static checks doubled from four to eight and test coverage hit 100%.

Here are the primary architectural lessons, failure modes, and trade-offs discovered while adapting a production MLOps codebase for AI agents.

## Dual Command Lists Are Agent Traps: The Single-Gate Pattern

The single largest source of agent confusion in legacy codebases is command duplication. When local git hooks run `pre-commit`, developers run `just test`, and CI enumerates custom shell steps in YAML, those lists inevitably drift.

During our audit, we discovered that secondary CI lists had silently dropped `mise run build`, while a Cookiecutter bake test executed every generated task except `pytest` — shipping a template whose own CI had never executed its test suite.

For an AI agent, this drift is fatal. An agent relies on feedback loops: if a check passes locally but fails in CI (or vice-versa), the agent enters hallucination loops attempting to reconcile two different sources of truth.

### The Solution: One Named Gate

We eliminated per-environment scripts in favor of a single machine-readable task vocabulary powered by `mise`:

```toml
[tasks.all]
alias = "a"
description = "Format, check, test, and build the project (the canonical gate)"
run = ["mise run format", "mise run check", "mise run test", "mise run build"]
```

Git hooks (`lefthook`) now run its subtasks, while GitHub Actions CI workflows and AI agent instructions (`AGENTS.md`) invoke this exact task. CI asserts that the working tree remains byte-clean after execution.

A list of steps can omit one. A named gate cannot.

## Prose Does Not Execute: Natural Language Rules vs. Machine Enforcement

To guide agents through complex repositories, the Linux Foundation stewarded standard [`AGENTS.md`](https://agents.md/) has emerged as the canonical entry point. It records operational context, non-obvious architecture rules, and definition-of-done criteria.

However, natural-language documentation suffers from an immediate failure mode: nothing executes it, so nothing catches its drift.

In our audit, we discovered that seven vendored agent skill files had drifted by up to 183 lines from their upstream sources. One skill was still instructing agents to run `just` and `pre-commit` months after those tools had been removed from the repository.

### The Boundary Rule

`AGENTS.md` must guide intent, but types, tests, linters, and static gates must enforce correctness.

To prevent documentation decay:

1. We deleted vendored skill copies and pointed `AGENTS.md` directly at single-source-of-truth repositories.
2. We added automated checks requiring every command, path, and tool version cited in an agent skill to exist in the target implementation.

## Database State in Agentic Testing: MLflow on SQLite

When MLflow 3 deprecated its legacy local file store in favor of relational tracking (`sqlite:///mlflow.db`), we faced a choice: maintain opt-in legacy fallbacks or adopt production-shaped storage defaults.

Moving `MlflowService` to SQLite exposed a severe performance bottleneck during automated test runs:

```python
# Default tracking URI in MLflow 3
DEFAULT_TRACKING_URI = "sqlite:///mlflow.db"
```

Running database migrations for every isolated unit test ballooned our test suite duration from 34 seconds to 339 seconds (a 10x slowdown).

### The Template Database Pattern

To maintain isolated, production-identical database state without the 10x latency penalty, we implemented a session-scoped database template pattern:

1. A session-scoped pytest fixture executes MLflow migrations once against a blank SQLite template database file.
2. Individual test cases perform a fast file-level copy of the pre-migrated SQLite database into a temporary directory.

This reduced test suite overhead by ~60% while ensuring every test runs against a true relational schema — verifying model registration, alias promotion to `Champion`, and artifact tracking under production conditions.

## Lockfile Decay & The Vulnerability Clock

A clean codebase with zero new commits will still rot over time due to upstream ecosystem shifts.

One month after tagged release `v5.0.0`, running our static vulnerability check (`trivy` + `pip-audit`) returned red: 25 known vulnerabilities introduced across transitive dependencies of MLflow.

The root cause was a dependency conflict: `cryptography` 50.0.0 patched security flaw `PYSEC-2026-3552`, but MLflow pinned `cryptography<50`, preventing standard resolvers from updating the package.

### Override Proofs vs. Scanner Suppression

Silencing security scanners or adding blanket ignores creates hidden operational risk. Instead, we established explicit override assertions in `pyproject.toml`:

```toml
[tool.uv]
override-dependencies = ["cryptography>=50"]
```

We then validated the override in both directions:

- Proving the full suite and model deployment pipeline pass cleanly with the override active.
- Asserting that removing the override correctly fails the security audit.

## Hard Engineering Trade-offs & Limitations

Building an agent-native, zero-warning codebase requires acknowledging explicit trade-offs:

- **Type Checking (`ty`)**: Astral's `ty` is pre-1.0 and does not yet fully model dynamic Pydantic/Pandera schemas. We ignore 6 rule categories globally and retain `mypy` as a baseline fallback.
- **Dependency Resolution**: `pandas 3.0` is released, but MLflow caps `pandas<3` and `numba` caps `numpy<2.5`. We accept latest compatible resolution over naive latest version.
- **Gate Latency**: Full gate execution (`mise run all`) takes 1.5 to 3.5 minutes due to 8 static scanners. We run formatters and static checks on pre-commit, and delegate tests to pre-push and the full gate to CI.

## Conclusion: Checklist for Agent-Native Codebases

If you are preparing a complex Python/ML repository for AI coding agents:

1. **Unify the Gate**: Expose exactly one entry point (`mise run all`) used identically by developers, CI, and agents, with git hooks running its subtasks.
2. **Treat `AGENTS.md` as Guidance, Not Enforcement**: Validate prose assertions against executable code via static linters and build checks.
3. **Prove Security Overrides**: Never suppress vulnerability scanners; use explicit dependency overrides validated against unit tests.
4. **Isolate State Deterministically**: Use template copy patterns for local databases (like SQLite) to keep test feedback fast for agents.

By turning your repository into a deterministic environment with unambiguous feedback, AI coding agents spend less time fighting tool drift and more time landing correct code.
