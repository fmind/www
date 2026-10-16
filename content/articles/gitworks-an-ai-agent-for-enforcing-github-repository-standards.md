+++
title = "GitWorks: an AI Agent for Enforcing GitHub Repository Standards"
description = "A Python notebook agent that reviews GitHub repositories against your own guidelines automatically, using Google Colab, the GitHub API, and Gemini models."
date = "2025-04-14"
tags = ["Coding", "Project"]
slug = "gitworks-an-ai-agent-for-enforcing-github-repository-standards"
syndicated = "https://medium.com/@fmind/gitworks-an-ai-agent-for-enforcing-github-repository-standards-e0193f60981d"
draft = false
+++

Maintaining consistency and quality across software projects, especially in collaborative environments, is a significant challenge. As projects grow and teams evolve, ensuring adherence to established coding standards, best practices, and [MLOps maturity levels](https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning) becomes increasingly complex. Manually reviewing repositories against detailed checklists is time-consuming, prone to inconsistency, and often falls behind the pace of development.

As an AI Engineer passionate about practical AI applications and MLOps, I frequently encounter this challenge. How can we automate the review process to ensure our GitHub repositories consistently meet defined guidelines, from basic structure to [advanced MLOps practices](https://mlops-coding-course.fmind.dev/)? This question led me to develop [**GitWorks**](https://github.com/fmind/GitWorks), a [Python notebook agent](https://github.com/fmind/GitWorks/blob/main/GitWorks_Automatically_Review_GitHub_Projects_with_Your_Guidelines.ipynb) designed to automatically review GitHub projects against your custom guidelines using the power of Generative AI.

Similar to my previous projects, [BKFC for Google Chat knowledge extraction](https://fmind.medium.com/bkfc-an-agentic-workflow-for-gathering-knowledge-from-google-chat-b521cba535d7) and [GenV for Google Meet video analysis](https://fmind.medium.com/genv-an-agentic-workflow-for-actionable-insights-from-google-meet-recordings-746d465fb827), GitWorks leverages accessible tools like [Google Colab](https://colab.research.google.com/), the [GitHub API](https://docs.github.com/en/rest), and [Google’s Gemini models](https://ai.google.dev/gemini-api/docs/models) to create a focused, [agentic workflow](https://www.youtube.com/watch?v=Qd6anWv0mv0) solving a specific, real-world problem.

![GitWorks: an AI Agent for Enforcing GitHub Repository Standards](/static/img/articles/gitworks-an-ai-agent-for-enforcing-github-repository-standards/cover.webp)

### The Motivation: From Manual Checks to Automated Compliance

In any software development lifecycle, adhering to standards is crucial for reliability, maintainability, and collaboration. For instance, [MLOps Guidelines](https://mlops-coding-course.fmind.dev/) might cover aspects like:

- Repository structure and essential files (`README.md`, `.gitignore`, `LICENSE`)
- Dependency management (`pyproject.toml`, `requirements.txt`)
- Code quality (linting, formatting, typing)
- Testing (setup, coverage)
- Automation (pre-commit hooks, CI/CD workflows)
- MLOps specific practices (configuration management, experiment tracking, model registry usage, security scanning)

Manually verifying these across multiple repositories is tedious. GitWorks aims to automate this verification, providing quick, consistent feedback directly within the development workflow.

### How GitWorks Works: An Agentic Workflow for Repository Review

GitWorks operates through a clear agentic process: **Define -\> Fetch -\> Analyze -\> Report**.

**Define Guidelines (Configuration):** The core of GitWorks is _your_ set of guidelines. You define these in a clear text format (e.g., the MLOps Code Repository Checklist provided in the notebook). This tells the agent _what_ to look for.

```markdown
## MLOps Code Repository Checklist

This checklist helps assess the maturity of an MLOps project based on artifacts and configurations found within its GitHub repository.

---

### Level 1: Prototype

_Focus: Basic functionality, primarily for project actors._

- **Repository Initialization:** `.git` directory exists, indicating version control is used.
- **Basic Code Structure:** Source code files exist (e.g., `.py` files or notebooks).
- **Initial README:** A basic `README.md` file exists, perhaps with a project title and brief description.
- **Environment/Dependency Listing (Basic):** A `requirements.txt` or initial `pyproject.toml` might exist, listing key dependencies.

---
```

**Setup & Authentication:** Standard setup involves obtaining API keys/tokens for GitHub and Gemini. These are securely stored using Colab’s secrets management. The script uses the `PyGithub` library for GitHub interactions and `google-genai` for Gemini.

```python
# GitHub
github_auth = gh.Auth.Token(GITHUB_ACCESS_TOKEN)
github = gh.Github(auth=github_auth)
# Gemini
genai_client = genai.Client(api_key=GEMINI_API_KEY)
```

**Fetch Repository Contents (Perception):** The agent connects to the specified GitHub repository using the provided token. It recursively fetches the content of all files in the repository, handling potential decoding errors. All file contents are concatenated into a single string context.

```python
repository = github.get_repo(REPOSITORY)
contents = []
stack = repository.get_contents("")
while stack:
    content = stack.pop(0)
    if content.type == "dir":
        new_contents = repository.get_contents(content.path)
        stack.extend(new_contents)
    else:
        contents.append(content)

string = io.StringIO()
for content in contents:
    path = content.path
    try:
        text = content.decoded_content.decode()
        part = f"--- file: {path} ---\n{text}\n"
        string.write(part)
    except Exception as error:
        print(f'[ERROR] Path: "{path}", Error: {error}')
string = string.getvalue()
```

**Analyze Contents (Reasoning & Action):** This is where Gemini comes in. The concatenated repository content is sent to the Gemini model (`gemini-2.0-flash` is a suitable choice) along with a system prompt instructing it to act as a Senior Software Engineer and review the code against the provided guidelines. Crucially, the prompt asks for a structured output: a summary of the review and a list of specific guidelines needing improvement, with suggestions for fixes. The desired output format is defined using a Pydantic model (`GitHubIssue`) to ensure the response is structured JSON containing a `title` and `body`.

```python
class GitHubIssue(pdt.BaseModel):
    """GitHub Issue."""
    title: str
    body: str

instructions = f"""
You are a Senior Software Engineer.
Given the following guidelines, give a detailed review the repository content.
Provide a general summary, and then lists the guidelines that need improvements and how to fix it.

{guidelines}
"""

review = genai_client.models.generate_content(
    model=MODEL,
    contents=string,
    config=gt.GenerateContentConfig(
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        system_instruction=instructions,
        response_mime_type='application/json',
        response_schema=GitHubIssue,
    ),
)
```

**Report Results (Output):** The structured JSON response from Gemini is parsed back into the Pydantic object. The review (`title` and `body`) is displayed in Markdown format within Colab. Optionally, if `CREATE_ISSUE` is set to `True`, the agent uses the GitHub API to automatically create a new issue in the target repository containing the review title and body.

```python
if CREATE_ISSUE:
    issue = repository.create_issue(title=review.parsed.title, body=review.parsed.body)
    print('Issue created:', issue.html_url)
```

### The Value Proposition: Why Use GitWorks?

This focused agent delivers significant advantages:

- **Automated Guideline Enforcement:** Ensures consistent application of your standards across projects.
- **Efficiency:** Drastically reduces the time spent on manual repository reviews.
- **Actionable Feedback:** Provides specific, structured feedback on areas needing improvement, directly in the repository as an issue.
- **Customizable:** Works with _your_ specific guidelines, adaptable to any project type or standard.
- **Low Price**: For a [relatively large ML repository](https://github.com/fmind/mlops-python-package) of 1,072,299 characters, the review cost \$0.05 using [Gemini 2.0 Flash](https://ai.google.dev/gemini-api/docs/pricing#gemini-2.0-flash).
- **Practical AI Application:** Demonstrates how GenAI can automate complex analysis and reporting tasks based on code content and defined rules.

### Conclusion: Empowering Development with AI-Driven Reviews

GitWorks provides a new practical example of how agentic workflows, powered by Generative AI, can automate and enhance crucial software development processes. By combining the data access capabilities of the GitHub API with the analytical power of Gemini models guided by custom instructions and structured schemas, we can transform the tedious task of repository review into an automated, efficient feedback loop.

It underscores that AI’s value isn’t limited to complex conversational systems; focused, task-specific agents like GitWorks can deliver immediate, tangible benefits by automating routine checks and enforcing standards. For developers and MLOps practitioners, tools like this make it easier to maintain high quality and consistency across projects, freeing up time for more complex challenges.

How else could AI agents assist in enforcing standards or automating reviews in your development workflow? Share your thoughts!

**Find the notebook on GitHub:** [https://github.com/fmind/GitWorks](https://github.com/fmind/GitWorks/tree/main)

![GitWorks: an AI Agent for Enforcing GitHub Repository Standards](/static/img/articles/gitworks-an-ai-agent-for-enforcing-github-repository-standards/02.webp)
