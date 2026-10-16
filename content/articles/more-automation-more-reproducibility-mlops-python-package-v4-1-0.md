+++
title = "More Automation + More Reproducibility = MLOps Python Package v4.1.0"
description = "The MLOps Python Package is your go-to solution for building robust and reproducible AI/ML workflows. Check out the latest v4.1.0 release!"
date = "2025-03-06"
tags = ["MLOps", "Python", "Project"]
slug = "more-automation-more-reproducibility-mlops-python-package-v4-1-0"
syndicated = "https://medium.com/@fmind/more-automation-more-reproducibility-mlops-python-package-v4-1-0-ba62ac1897f4"
draft = false
+++

The [**MLOps Python Package**](https://github.com/fmind/mlops-python-package) is your go-to solution for building robust and reproducible machine learning workflows. With the latest v4.1.0 release, we’ve doubled down on automation and reproducibility, making your MLOps journey smoother than ever.

![Credit to ashishpatel26 for the diagram and his contribution!](/static/img/articles/more-automation-more-reproducibility-mlops-python-package-v4-1-0/cover.webp)

Credit to [ashishpatel26](https://github.com/ashishpatel26) for the diagram and his contribution!

### What’s New in v4.1.0?

This release introduces several key features that enhance automation and reproducibility:

#### 1. Switch from PyInvoke to Just

We’ve transitioned from [PyInvoke](https://www.pyinvoke.org/) to [Just](https://just.systems/) for managing our automation tasks. [Just](https://just.systems/) offers a cleaner and more concise syntax compared to [PyInvoke](https://www.pyinvoke.org/) and [GNU Make](https://www.gnu.org/software/make/manual/make.html), making it easier to read and maintain our workflows. You can now trigger actions directly from your command line or use the [Just VS Code extension](https://marketplace.visualstudio.com/items?itemName=nefrob.vscode-just-syntax) for a seamless development experience.

Here’s an example of the main [justfile](https://github.com/fmind/mlops-python-package/blob/v4.1.0/justfile):

```justfile
# https://just.systems/man/en/

# REQUIRES

docker := require("docker")
find := require("find")
rm := require("rm")
uv := require("uv")

# SETTINGS

set dotenv-load := true

# VARIABLES

PACKAGE := "bikes"
REPOSITORY := "bikes"
SOURCES := "src"
TESTS := "tests"

# DEFAULTS

# display help information
default:
    @just --list

# IMPORTS

import 'tasks/check.just'
import 'tasks/clean.just'
import 'tasks/commit.just'
import 'tasks/doc.just'
import 'tasks/docker.just'
import 'tasks/format.just'
import 'tasks/install.just'
import 'tasks/mlflow.just'
import 'tasks/package.just'
import 'tasks/project.just'
```

And one of the task files ([tasks/check.just](https://github.com/fmind/mlops-python-package/blob/v4.1.0/tasks/check.just))

```justfile
# run check tasks
[group('check')]
check: check-code check-type check-format check-security check-coverage

# check code quality
[group('check')]
check-code:
    uv run ruff check {{SOURCES}} {{TESTS}}

# check code coverage
[group('check')]
check-coverage numprocesses="auto" cov_fail_under="80":
    uv run pytest --numprocesses={{numprocesses}} --cov={{SOURCES}} --cov-fail-under={{cov_fail_under}} {{TESTS}}

# check code format
[group('check')]
check-format:
    uv run ruff format --check {{SOURCES}} {{TESTS}}

# check code security
[group('check')]
check-security:
    uv run bandit --recursive --configfile=pyproject.toml {{SOURCES}}

# check unit tests
[group('check')]
check-test numprocesses="auto":
    uv run pytest --numprocesses={{numprocesses}} {{TESTS}}

# check code typing
[group('check')]
check-type:
    uv run mypy {{SOURCES}} {{TESTS}}
```

#### 2. Gemini Code Assist for GitHub PR Reviews

Say hello to your new AI-powered code reviewer! We’ve integrated [Gemini Code Assist](https://developers.google.com/gemini-code-assist/docs/review-github-code) to help you streamline your pull request review process. Gemini can automatically suggest code improvements, identify potential issues, and even summarize PR changes, saving you valuable time and effort.

Here is an example of [a Gemini Code Assist review on GitHub](https://github.com/fmind/mlops-python-package/pull/52#pullrequestreview-2662381245):

> This pull request introduces several enhancements, including Gemini code assist support, Dependabot configuration, and default GitHub rulesets. The changes appear well-structured and contribute to improved automation and security. However, there are a few areas that could benefit from further attention.

> **Summary of Findings**

> Missing Error Handling in `install-rulesets` task: The `install-rulesets` task in `tasks/install.just` lacks error handling for the `gh api` command. If the API call fails, the script will not report the error, potentially leading to undetected deployment issues.

> README.md Updates: The README.md file was updated to include new tools, but it would be beneficial to add more context around the usage of these tools and how they integrate into the project’s workflow.

> **Merge Readiness**

> The pull request is almost ready for merging. Addressing the missing error handling in the `install-rulesets` task is crucial. Additionally, enhancing the README.md with more detailed information about the new tools would be beneficial. I am unable to directly approve the pull request, and recommend that others review and approve this code before merging. At a minimum, the critical and high severity comments should be addressed before merging.

> Consider adding error handling to the `gh api` command to ensure that deployment failures are detected and reported. This can be done by checking the exit code of the command and logging an error message if it is non-zero.

> gh api --method POST -H "Accept: application/vnd.github+json" \\\
>  "/repos/\$owner/\$repo/rulesets" --input=".github/rulesets/main.json" \|\| echo "Failed to install rul

#### 3. Automatic GitHub Rulesets Push

Maintaining consistent code quality and security practices is crucial for any MLOps project. With this release, we’ve automated the process of pushing [GitHub rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets). This ensures that your codebase adheres to predefined standards, reducing the risk of errors and vulnerabilities.

Here’s an example of a [GitHub ruleset applied on the project main branch](https://github.com/fmind/mlops-python-package/blob/main/.github/rulesets/main.json):

```json
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "exclude": [],
      "include": [
        "~DEFAULT_BRANCH"
      ]
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "required_linear_history"
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": [
          "squash",
          "rebase"
        ]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          {
            "context": "checks",
            "integration_id": 15368
          }
        ]
      }
    },
    {
      "type": "non_fast_forward"
    }
  ],
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    }
  ]
}
```

#### 4. Deterministic Python Wheel with constraints.txt

Reproducibility is paramount in MLOps. To ensure consistent builds, we’ve introduced a `constraints.txt` file that captures the exact versions of all dependencies. This guarantees that your Python wheels are built with the same dependencies every time, eliminating potential inconsistencies.

Here’s an example of a [`constraints.txt`](https://github.com/fmind/mlops-python-package/blob/v4.1.0/constraints.txt) file for the project:

```text
# This file was autogenerated by uv via the following command:
#    uv pip compile pyproject.toml --generate-hashes --output-file=constraints.txt
alembic==1.14.1 \
    --hash=sha256:1acdd7a3a478e208b0503cd73614d5e4c6efafa4e73518bb60e4f2846a37b1c5 \
    --hash=sha256:496e888245a53adf1498fcab31713a469c65836f8de76e01399aa1c3e90dd213
    # via mlflow
annotated-types==0.7.0 \
    --hash=sha256:1f02e8b43a8fbbc3f3e0d4f0f4bfc8131bcb4eebe8849b8e5c773f3a1c582a53 \
    --hash=sha256:aff07c09a53a08bc8cfccb9c85b05f1aa9a2a6f23728d790723543408344ce89
    # via pydantic
antlr4-python3-runtime==4.9.3 \
    --hash=sha256:f224469b4168294902bb1efa80a8bf7855f24c99aef99cbefc1bcd3cce77881b
    # via omegaconf
blinker==1.9.0 \
    --hash=sha256:b4ce2265a7abece45e7cc896e98dbebe6cead56bcf805a3d23136d145f5445bf \
    --hash=sha256:ba0efaa9080b619ff2f3459d1d500c57bddea4a6b424b60a91141db6fd2f08bc
    # via flask
```

[And the Just task to generate and install the constraints.txt file](https://github.com/fmind/mlops-python-package/blob/v4.1.0/tasks/package.just):

```justfile
# run package tasks
[group('package')]
package: package-build

# build package constraints
[group('package')]
package-constraints constraints="constraints.txt":
 uv pip compile pyproject.toml --generate-hashes --output-file={{constraints}}

# build python package
[group('package')]
package-build constraints="constraints.txt": clean-build package-constraints
 uv build --build-constraint={{constraints}} --require-hashes --wheel
```

### Upgrade Today and Experience the Difference!

Ready to take your MLOps workflows to the next level? Upgrade to [**MLOps Python Package**](https://github.com/fmind/mlops-python-package) [v4.1.0](https://github.com/fmind/mlops-python-package/releases) and unlock the power of enhanced automation and reproducibility.

To make these improvements even more accessible, we’ve also updated the [**Cookiecutter MLOps Package**](https://github.com/fmind/cookiecutter-mlops-package). This template provides a pre-configured project structure and CI/CD pipeline, allowing you to quickly bootstrap new MLOps projects with all the latest features. You can generate a new project with the updated template by running:

```bash
pip install cookiecutter
cookiecutter gh:fmind/cookiecutter-mlops-package
```

In the coming days, we will also update the [**MLOps Coding Course**](https://github.com/MLOps-Courses/mlops-coding-course) and the [**MLOps Coding Assistant**](https://mlops-coding-assistant.fmind.dev/). Follow me on [X](https://x.com/fmind_dev), [GitHub](https://github.com/fmind), [Medium](https://fmind.medium.com/), [LinkedIn](https://www.linkedin.com/in/fmind-dev/) to stay tuned!

![Photo by Lenny Kuhne on Unsplash](/static/img/articles/more-automation-more-reproducibility-mlops-python-package-v4-1-0/02.webp)

Photo by [Lenny Kuhne](https://unsplash.com/@lennykuhne?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)
