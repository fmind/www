+++
title = "mAIdAI: Building a Personal Assistant with Google Cloud and Vertex AI"
description = "Build a personal AI assistant using Google Cloud Run, Vertex AI, and Google Chat. A guide to architecting context-aware agents."
date = "2026-02-05"
tags = ["Agent", "Cloud", "Project"]
slug = "maidai-building-a-personal-assistant-with-google-cloud-and-vertex-ai"
syndicated = "https://medium.com/@fmind/maidai-building-a-personal-assistant-with-google-cloud-and-vertex-ai-a136aa73656b"
draft = false
+++

As an AI Architect, I spend my days designing AI systems and agents for others. I optimize workflows, fine-tune context windows, and architect serverless solutions to solve complex business problems.

But recently, I caught myself in a classic “cobbler’s children” scenario. While helpful bots supported my teams, I navigated my own workflow manually — answering the same repetitive questions, digging for the same documentation links, and context-switching constantly.

I realized I needed something different. Not another generic team bot, but a **Personal AI Assistant** — one that knows _my_ specific context, _my_ preferred shortcuts, and _my_ tone.

So I built **mAIdAI** (My AI Aid)**:** [https://github.com/fmind/maidai](https://github.com/fmind/maidai)

![mAIdAI Avatar (Source: Gemini App)](/static/img/articles/maidai-building-a-personal-assistant-with-google-cloud-and-vertex-ai/cover.webp)

mAIdAI Avatar (Source: Gemini App)

In this article, I’ll walk you through how I architected this personal agent using **Google Chat**, **Cloud Run**, and **Vertex AI**.

### The Problem: The High Cost of “Quick” Tasks

We often underestimate the micro-friction in our daily work.

- “Where is the design doc for Project X?”
- “What’s the syntax for that specific gcloud command again?”
- “Can you review this snippet?”

Standard team bots are great, but they are generic. They lack the _specific_ context of your personal role and responsibilities. I wanted an agent that acts as a “Second Brain” — grounded in my personal knowledge and capable of executing my specific workflows.

### The Solution: mAIdAI Pattern

mAIdAI is designed around three core interaction types:

1. **Context-Aware Chat**: A conversational flow grounded in a personal `context.md` file effective “system instructions”.
2. **Quick Commands**: Instant helpers that return static values (like commonly used links or snippets) without invoking the LLM.
3. **Slash Commands**: specialized triggers that wrap user input in a predefined prompt template (e.g., `/fix` to debug code).

![Demo of mAIdAI on Google Chat (Generic Version)](/static/img/articles/maidai-building-a-personal-assistant-with-google-cloud-and-vertex-ai/02.webp)

Demo of mAIdAI on Google Chat (Generic Version)

![About mAIdAI](/static/img/articles/maidai-building-a-personal-assistant-with-google-cloud-and-vertex-ai/03.webp)

About mAIdAI

### Architecture

The system follows a lightweight, serverless event-driven architecture.

![Architecture Diagram of mAIdAI (Source: Fmind.dev)](/static/img/articles/maidai-building-a-personal-assistant-with-google-cloud-and-vertex-ai/04.webp)

Architecture Diagram of mAIdAI (Source: Fmind.dev)

### The Flow

1. **Frontend**: usage of the **Google Chat** app interface. No custom UI to build or maintain.
2. **Transport**: Chat events are delivered via HTTP webhooks.
3. **Backend**: A **Cloud Run** service hosting a FastAPI application processes the events.
4. **Intelligence**: The backend connects to **Vertex AI** (Gemini models) for reasoning, grounded by the personal context file.

### Deep Dive: The Code

The implementation is surprisingly minimal, thanks to the **Google GenAI SDK** and **FastAPI**. The entire core logic resides in a single `main.py` file.

### 1. The Setup

We initialize the GenAI client using standard environment variables. This keeps the code portable and secure.

```python
# main.py
client = genai.Client(
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
    vertexai=True,
)

# Loading the Second Brain
MODEL_CONTEXT = (ROOT_FOLDER / "context.md").read_text()
config = types.GenerateContentConfig(
    system_instruction=MODEL_CONTEXT,
    max_output_tokens=5000,
)
```

By reading `context.md` at startup and injecting it as the `system_instruction`, we ensure every interaction is grounded in my specific reality.

### 2. Handling Interaction Types

The core router handles the distinction between simple commands and AI interactions. This is crucial for latency and cost — not every interaction needs a round-trip to an LLM.

```python
@app.post("/")
async def index(request: Request) -> dict:
    event = await request.json()
    # ... extraction logic ...

    if command_id := app_command_metadata.get("appCommandId"):
        # Handle Slash and Quick Commands
        if command_type == "QUICK_COMMAND":
            return respond(command_text)

        if command_type == "SLASH_COMMAND":
            # Contextualize the prompt
            prompt = f"{command_text}. USER INPUT: {user_input}"
            return respond(await chat(prompt))

    # Fallback to standard chat
    return respond(await chat(user_input))
```

This pattern allows me to have a `/links` command that returns immediately (0 latency, 0 cost), while a `/rewrite` command leverages Gemini 2.0 Flash for creative work.

### 3. Asynchrony by Default

Using `async def` and `client.aio.models.generate_content` ensures the Cloud Run container can handle multiple concurrent requests efficiently, even with a single instance.

### Deployment Strategy

Simplicity was the primary constraint. I didn’t want to manage infrastructure for a personal tool.

- **Runtime**: Cloud Run (fully managed, scales to zero, low-cost serving).
- **Configuration**: Environment variables for model selection (`gemini-3-flash`) and project details.
- **Security**: IAM-based authentication ensures only verified chat events reach the service.

### Why Build This Locally?

You might ask, “Why not use a standard consumer AI chat?”

1. **Privacy**: Data stays within my Google Cloud project.
2. **Context**: I control the system prompt (`context.md`) explicitly.
3. **Workflow Integration**: It lives where I work — in Google Chat — not a separate browser tab.

### Conclusion

We often accept friction because “it’s just how things are.” But as engineers, we have the tools to change that. mAIdAI is a proof of concept that a highly personalized, context-aware agent doesn’t require a massive engineering team. It just requires a few hundred lines of Python and the right cloud primitives.

If you find yourself copying the same text or answering the same questions repeatedly, maybe it’s time to build your own assistant.

![Source: Gemini App](/static/img/articles/maidai-building-a-personal-assistant-with-google-cloud-and-vertex-ai/05.webp)

Source: Gemini App
