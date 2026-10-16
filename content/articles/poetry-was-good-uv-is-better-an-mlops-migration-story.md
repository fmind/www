+++
title = "Poetry Was Good, Uv Is Better: An MLOps Migration Story"
description = "Poetry to Uv: A faster, simpler way to manage dependencies for MLOps projects."
date = "2025-01-27"
tags = ["MLOps", "Python"]
slug = "poetry-was-good-uv-is-better-an-mlops-migration-story"
syndicated = "https://medium.com/@fmind/poetry-was-good-uv-is-better-an-mlops-migration-story-f52bf0c6c703"
draft = false
+++

As an MLOps Engineer, I’m always on the lookout for tools and technologies that can streamline workflows, boost performance, and enhance the maintainability of MLOps projects. Recently, I made a significant shift in the [MLOps Python Package ](https://github.com/fmind/mlops-python-package)— a repository dedicated to sharing best practices for MLOps in Python. I transitioned from [Poetry](https://python-poetry.org/), a popular dependency management and packaging tool, to [Uv](https://docs.astral.sh/uv/), a newer, blazing-fast alternative.

![Photo by Chris Briggs on Unsplash](/static/img/articles/poetry-was-good-uv-is-better-an-mlops-migration-story/cover.webp)

Photo by [Chris Briggs](https://unsplash.com/@cgbriggs19?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

This wasn’t a decision I took lightly. Poetry has served my teammates and me well on many MLOps projects, but Uv’s promise of enhanced speed and stricter adherence to Python Enhancement Proposals (PEPs) piqued our interest. **After thoroughly testing it out, we were convinced. The transition is a resounding success, and we’re excited to share our experience and why we believe Uv might be the right choice for your AI/ML projects too.**

### The Need for Speed (and PEPs)

The “[MLOps Python Package](https://github.com/fmind/mlops-python-package)” is a side project, but it reflects the best practices defined in the organizations I’m working with. As our MLOps projects grew, we started noticing that dependency resolution and installation with Poetry were becoming increasingly sluggish. **This was particularly noticeable in our CI/CD pipelines with runs often exceeding 25 minutes**. Moreover, while Poetry is a powerful tool, it sometimes requires its own configurations, deviating from [standard PEP practices](https://peps.python.org/pep-0621/).

Enter [Uv](https://docs.astral.sh/uv/). This new tool, developed by [Astral](https://astral.sh/), promised to be a drop-in replacement for `pip`, `pip-tools`, `pipx`, `poetry`, `pyenv`, `twine`, and `virtualenv`, boasting significant speed improvements thanks to its Rust foundation. It also claimed [strict compliance with PEPs](https://peps.python.org/pep-0621/), which meant a more standardized and potentially less complex project structure.

### The Transition: Smooth Sailing with Uv

Migrating from Poetry to Uv was surprisingly straightforward. The most interesting part was adapting our [pyproject.toml](https://github.com/fmind/mlops-python-package/blob/main/pyproject.toml), [CI/CD workflows (GitHub Actions in our case)](https://github.com/fmind/mlops-python-package/tree/main/.github/workflows), [development tasks](https://github.com/fmind/mlops-python-package/tree/v3.0.0/tasks) and [Dockerfile](https://github.com/fmind/mlops-python-package/blob/main/Dockerfile).

#### A Cleaner, More Compliant `pyproject.toml`

The move to Uv brought welcome changes to our [`pyproject.toml`](https://github.com/fmind/mlops-python-package/blob/main/pyproject.toml) file. We were able to remove the Poetry-specific sections, like `[tool.poetry]` and its associated configurations:

```toml
[tool.poetry]
name = "bikes"
version = "2.0.0"
description = "Predict the number of bikes available."
...
[tool.poetry.dependencies]
python = "^3.12"
loguru = "^0.7.2"
...
[tool.poetry.group.checks.dependencies]
bandit = "^1.7.9"
...
```

Now we could rely solely on [standards-compliant sections](https://peps.python.org/pep-0621/) like `[project]` and `[project.optional-dependencies]`:

```toml
[project]
name = "bikes"
version = "3.0.0"
description = "Predict the number of bikes available."
...
dependencies = [
    "loguru>=0.7.2",
    ...
]
...
[dependency-groups]
checks = [
    "bandit>=1.8.0",
    ...
]
```

**GitHub Actions: Setup**

Previously, our [setup action](https://github.com/fmind/mlops-python-package/blob/v3.0.0/.github/actions/setup/action.yml) involved installing `pipx`, `invoke`, and `poetry`:

```yaml
- run: pipx install invoke poetry
  shell: bash
- uses: actions/setup-python@v5
  with:
    python-version: 3.12
    cache: poetry
```

With Uv we simply need to adopt a new GitHub Action:

```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v4
  with:
    enable-cache: true
- name: Setup Python
  uses: actions/setup-python@v5
  with:
    python-version-file: .python-version
```

The [`astral-sh/setup-uv`](https://github.com/astral-sh/setup-uv) action made installing Uv incredibly simple, and we could rely on the action to specify the python version in the `.python-version` file.

**GitHub Actions: Checks and Publishing**

Our [check workflow](https://github.com/fmind/mlops-python-package/blob/v3.0.0/.github/workflows/check.yml) also saw few changes. Instead of running a single checker step with Poetry:

```yaml
- run: poetry install --with checks
- run: poetry run invoke checks
```

We now have separate checkers with Uv to improve speed and debugging:

```yaml
- run: uv sync --group=checks
- run: uv run invoke checks.format
- run: uv run invoke checks.type
- run: uv run invoke checks.code
- run: uv run invoke checks.security
- run: uv run invoke checks.coverage
```

Similarly, in our [publishing workflow](https://github.com/fmind/mlops-python-package/blob/v3.0.0/.github/workflows/publish.yml), `poetry install --with docs` and `poetry run invoke docs` became `uv sync --group=docs` and `uv run invoke docs`, respectively. These changes highlight Uv's ability to seamlessly integrate into existing workflows while being faster than Poetry.

**Development Tasks**

Our pyinvoke [tasks](https://github.com/fmind/mlops-python-package/tree/v3.0.0/tasks), defined in the `tasks/` directory, also required only minor changes. For instance, our [installation](https://github.com/fmind/mlops-python-package/blob/v3.0.0/tasks/installs.py) and [format](https://github.com/fmind/mlops-python-package/blob/v3.0.0/tasks/formats.py) task went from:

```python
@task
def poetry(ctx: Context) -> None:
    """Install poetry packages."""
    ctx.run("poetry install")

@task
def format(ctx: Context) -> None:
    """Check the formats with ruff."""
    ctx.run("poetry run ruff format --check src/ tasks/ tests/")
```

With Uv it becomes:

```python
@task
def uv(ctx: Context) -> None:
    """Install uv packages."""
    ctx.run("uv sync --all-groups")

@task
def format(ctx: Context) -> None:
    """Check the formats with ruff."""
    ctx.run("uv run ruff format --check src/ tasks/ tests/")
```

#### Slimmer, Faster Docker Builds with Uv

The benefits of Uv extend into our Docker builds as well. Our initial `Dockerfile` relied on installing the package wheel using `pip`:

```dockerfile
FROM python:3.12
COPY dist/*.whl .
RUN pip install *.whl
CMD ["bikes", "--help"]
```

This was functional but not optimal. With Uv, we were able to switch to a more streamlined approach, leveraging Uv’s speed within the Docker build process. We also switched to the official `uv` image maintained by Astral:

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm
COPY dist/*.whl .
RUN uv pip install --system *.whl
CMD ["bikes", "--help"]
```

The key change here is using `uv pip install --system *.whl` instead of `pip install *.whl`. By using the `--system` flag, we ensure that the package and its dependencies are installed into the system's site packages directory, making for a cleaner environment. This, combined with Uv's installation speed, resulted in significantly faster Docker builds.

### The Results: Speed, Simplicity, and Standards

The impact of switching to Uv was immediately noticeable. **Our CI/CD pipelines became significantly faster, thanks to Uv’s rapid dependency resolution and installation.** Locally, development felt snappier too.

But it wasn’t just about speed. **Uv’s strict adherence to PEP standards meant we could simplify our project configuration**. We no longer needed a separate `poetry.toml` file. Everything was managed within the standard `pyproject.toml`, making our [project more aligned with the broader Python ecosystem](https://peps.python.org/pep-0621/).

### Why You Might Want to Consider Uv

Our experience with [Uv](https://docs.astral.sh/uv/) has been overwhelmingly positive. If you’re working on an MLOps project (or any Python project, for that matter) and value speed, simplicity, and adherence to standards, we highly recommend giving Uv a try. Here’s a quick recap of the benefits we observed:

- **Blazing Fast:** Uv’s Rust-based architecture delivers significant speed improvements over Poetry.
- **PEP Compliance:** Strict adherence to PEPs means a more standardized and potentially less complex project structure.
- **Seamless Integration:** Uv integrates smoothly into existing workflows, often simplifying them in the process.
- **Drop-in Replacement:** Uv can replace `pip`, `pip-tools`, `pipx`, `poetry`, `pyenv`, `twine`, `virtualenv`, and more, making it a versatile tool for various project needs.

### Conclusion: Embracing the Future of Python Dependency Management

The transition from Poetry to Uv in our “[MLOps Python Package](https://github.com/fmind/mlops-python-package)” project has been a rewarding experience. It’s a testament to the evolving landscape of Python tooling and the benefits of embracing new technologies that align with our goals of efficiency, maintainability, and community standards.

We encourage you to explore Uv and see if it’s the right fit for your projects. The future of Python dependency management is here, and it’s faster and more standardized than ever before!

![Photo by Harley-Davidson on Unsplash](/static/img/articles/poetry-was-good-uv-is-better-an-mlops-migration-story/02.webp)

Photo by [Harley-Davidson](https://unsplash.com/@harleydavidson?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)
