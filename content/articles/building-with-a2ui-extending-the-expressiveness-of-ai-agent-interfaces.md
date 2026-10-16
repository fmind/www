+++
title = "Building with A2UI: Extending the Expressiveness of AI Agent Interfaces"
description = "Building AI-First apps with A2UI: from the Agent-View-Controller (AVC) pattern to managing latency. A practical case study with Featest."
date = "2026-01-28"
tags = ["Agent", "LLM"]
slug = "building-with-a2ui-extending-the-expressiveness-of-ai-agent-interfaces"
syndicated = "https://medium.com/@fmind/building-with-a2ui-extending-the-expressiveness-of-ai-agent-interfaces-d380ceac2040"
draft = false
+++

In 2026, AI agents have become incredibly smart, yet they are often limited to simple chatbot interfaces. We have engines capable of reasoning, planning, and coding, but we force them to communicate results through text and basic markdown.

To unlock the full potential of agents, we need a better language for them to express themselves. We need agents that can project rich, dynamic, and interactive user interfaces that adapt to the user’s intent.

This is the promise of [**A2UI (Agent-to-User Interface)**](https://a2ui.org/): a protocol that allows agents to “speak” UI natively.

In my [previous article](https://fmind.medium.com/finding-the-holy-grail-of-ai-agent-uis-from-ai-orchestrated-development-to-a2ui), I explored the landscape of AI UI solutions and explained why A2UI stands out. Now, I wanted to put it to the test. I built [Featest](https://github.com/fmind/featest), a feature request application designed to be “AI-First.” Here is the story of how it was built, the strengths of the protocols I used, and the architectural patterns that emerged.

![Source: Gemini App](/static/img/articles/building-with-a2ui-extending-the-expressiveness-of-ai-agent-interfaces/cover.webp)

Source: Gemini App

### The Project: Featest

The origin of this project was a simple request from my Product Manager: _“We need a way for users to vote on features.”_

I could have built a standard CRUD app. But I saw this as an opportunity. A feature request board is dynamic. Users have vague intents: _“I want something like dark mode but for audio.”_ They want to merge duplicates. They want to see trends, and admins want to automatically tag requests.

This was the perfect scenario to consider an **AI-First experience**. I didn’t want a static form; I wanted an agent that users could talk to, which enhances the interactions, and uses the right UI tools when needed.

**Github Repository**: [Featest](https://github.com/fmind/featest)

![Suggest new features with AI (Source: Fmind.dev)](/static/img/articles/building-with-a2ui-extending-the-expressiveness-of-ai-agent-interfaces/02.webp)

Suggest new features with AI (Source: Fmind.dev)

### The Power Couple: A2UI and A2A

Before diving into the code, it’s critical to understand the two pillars of this architecture.

### 1. A2UI: Agent-to-User Interface (The Content)

A2UI is a **declarative protocol**. Instead of an agent writing code (which is risky and error-prone), it streams a structured JSON description of a UI.

Here is what it looks like on the wire. The agent sends `SurfaceUpdate` events to render components like a card with a button:

```json
{
  "surfaceUpdate": {
    "surfaceId": "main-surface",
    "components": [
      {
        "id": "welcome-card",
        "component": {
          "Card": {
            "child": "welcome-text"
          }
        }
      },
      {
        "id": "welcome-text",
        "component": {
          "Text": {
            "text": { "literalString": "Welcome to Featest" },
            "usageHint": "h1"
          }
        }
      }
    ]
  }
}
```

### 2. A2A: Agent-to-Agent Communication (The Transport)

[A2A](https://github.com/a2aproject/A2A) is the **transport protocol**. It standardizes how agents talk to each other and to clients over HTTP. It handles the handshake, the task lifecycle, and the message passing.

In Featest, the client wraps the user’s intent in an A2A message:

```http
POST /api/agents/feature_request_agent/tasks
Content-Type: application/json

{
  "task_id": "12345",
  "input": {
    "text": "I want to vote for dark mode"
  }
}
```

Together, they create a universal language. A2A carries the envelope, and A2UI ensures the letter inside contains rich, interactive content, not just text.

### Architecture

I designed the system to be modular, using the [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs) and the A2A protocol effectively.

![Architecture Diagram of the Featest App (Source: Fmind.dev)](/static/img/articles/building-with-a2ui-extending-the-expressiveness-of-ai-agent-interfaces/03.webp)

Architecture Diagram of the Featest App (Source: Fmind.dev)

The flow is bidirectional and relies on robust open-source packages:

1. **User** interacts with the **Lit Client**, which uses the official [`@a2ui/lit`](https://github.com/a2ui-project/a2ui/tree/main/typescript/renderers/lit) renderer. It acts as a state machine, processing `SurfaceUpdate` events to patch the DOM efficiently.
2. **Client** sends intent via **A2A** to the **Backend**. The `A2UIClient` wraps the user’s input (text or events) in a standard JSON-RPC envelope.
3. **Backend Agent** processes logic and streams back **A2UI** JSON instructions.
4. **Client** renders the UI components dynamically.

The power of this system comes from the **Component Schema**. Featest supports a rich set of native components defined in `schemas.py`, ensuring the agent has high-level building blocks rather than raw HTML:

- **Layout**: `Row`, `Column`, `List`, `Card`, `Tabs`, `Divider`, Modal.
- **Input**: `Button`, `CheckBox`, `TextField`, `DateTimeInput`, `MultipleChoice`, Slider.
- **Media**: `Text`, `Image`, `Icon`, `Video`, AudioPlayer.

### The AVC Pattern: Agent-View-Controller

The most significant discovery I made while building Featest was an architectural one.

When you start building complex agent apps, you quickly realize that a single agent doing everything (reasoning, database access, UI formatting) is a mess. It’s hard to test and hard to control.

I adopted what I call the **Agent-View-Controller (AVC) Pattern** — an evolution of [Model-View-Controller (MVC)](https://en.wikipedia.org/wiki/Model%E2%80%93view%E2%80%93controller) for the agent era.

### 1. The Controller Agent (The Brain)

This agent handles the business logic. It doesn’t care about pixels. It inputs a user request, decides which tool to use (e.g., `vote_feature`, `add_comment`), and outputs structured data.

```python
# agent/agent.py
controller_agent = agents.Agent(
    name="controller_agent",
    model=configs.AGENT_MODEL,
    description="Executes application logic.",
    instruction=prompts.CONTROLLER_INSTRUCTION,
    tools=[
        tools.list_features,
        tools.add_feature,
        tools.upvote_feature,
        tools.add_comment,
        tools.get_feature,
        tools.update_feature,
        tools.delete_feature,

    ],
)
```

### 2. The View Agent (The Renderer)

This agent is the designer. It takes the data from the Controller and translates it into A2UI JSON. It cares about layout, typography, and hierarchy.

```python
view_agent = agents.Agent(
    name="view_agent",
    model=configs.AGENT_MODEL,
    description="Formats data into A2UI schema.",
    instruction=prompts.VIEW_INSTRUCTION,
    output_schema=schemas.A2UI,
)
```

### 3. The Sequential Pipeline

I chained them together using ADK’s SequentialAgent. This simple composition gave me immense flexibility. I could swap the View Agent to change the entire look and feel of the app without touching a single line of business logic.

```python
root_agent = agents.SequentialAgent(
    name="feature_request_agent",
    description="Handles feature requests from users.",
    sub_agents=[controller_agent, view_agent],
)
```

### Strengths of the Protocol

Working with A2UI revealed several advantages over traditional chatbot approaches.

![Leave comment, with a form rendered dynamically with A2UI (Source: Fmind.dev)](/static/img/articles/building-with-a2ui-extending-the-expressiveness-of-ai-agent-interfaces/04.webp)

Leave comment, with a form rendered dynamically with A2UI (Source: Fmind.dev)

### 1. UI Language

We are used to agents speaking Markdown. Markdown is fantastic for content: paragraphs, lists, and code blocks. But it fails when you need _interaction_.

If an agent needs to ask for a complex set of preferences, Markdown forces it to ask one question at a time or parse a messy natural language blob. A2UI allows the agent to project a form with validation, sliders for precise values, and date pickers. It elevates the agent from a “writer” to an “interface designer,” matching the right interaction model to the user’s intent.

### 2. Security by Design

This is the enterprise killer feature. Because A2UI is **data**, not code, there is no `eval()` happening on the client. The agent selects from a catalog of safe, pre-built components. You can’t inject malicious scripts via A2UI, making it safe for production environments where “generated code” is a security nightmare.

### 3. Progressive Rendering

A2UI is designed to be streamed. As the LLM generates the JSON tokens, the UI builds itself on the screen.

- First, the container appears.
- Then, the title.
- Then, the list items one by one.

This makes the application feel incredibly responsive, masking some latency with visible progress.

### 4. Interoperability

Because the UI is just JSON, the exact same agent response can be rendered natively on the web (via [Lit](https://lit.dev/)), on mobile (via [Flutter](https://docs.flutter.dev/ai/genui)), or on iOS (via Swift). You build the agent intelligence once, and it projects natively everywhere.

### 5. Client Style Control

With A2UI, the agent is responsible for the _structure_ (intent), but the client is completely in control of the _style_.

The agent says “I need a primary button.” It doesn’t say “I need a blue button with 4px border radius.” This means your application maintains perfect brand consistency. The same agent response can look like a sleek consumer app on Android or a dense dashboard on the web, simply by changing the client-side theme.

### Limitations

### 1. Maturity & Boilerplate

A2UI is a new protocol. Building a custom app from scratch currently requires significant boilerplate code. For now, the best approach is to use packages like Flutter’s [GenUI SDK](https://docs.flutter.dev/ai/genui) or wait for higher-level integrations from ADK or Gemini Enterprise.

### 2. Latency vs. Smartness

Another major challenge is **latency**. Generating UI tokens takes time and money. While streaming and using “Fast Planners” (like I did in Featest) mitigate this, a pure agentic experience will never beat a hand-optimized native app for core, repetitive tasks. The “smartness” of the dynamic UI must outweigh the latency cost — if it doesn’t, just use a static button.

### 3. Complementary Nature

I also found that not every use case benefits from dynamic UI. For the core voting interaction in Featest, a static, predictable UI was simpler and faster. Where A2UI shines is for _augmenting_ the experience, helping users rationalize features, tag duplicates, or explore trends through conversation. In this project, it’s a powerful **complement** to a baseline UI, not necessarily a replacement.

### Conclusion

A2UI is a fantastic protocol, but it’s not a silver bullet.

In my case, I initially thought a pure “AI-First” app would be the ideal experience. However, I learned that for basic, repetitive tasks, it’s simply too slow compared to a traditional interface. The latency of generating UI on the fly doesn’t always pay off.

The ideal approach for this project is a **hybrid model**: mixing static, highly-optimized UIs for core workflows with dynamic, agentic components for complex, intent-driven tasks. It is up to the programmer to find the best trade-off for each specific use case.

However, for **chatbot-focused applications**, this solution could be highly valuable. It enables the creation of much richer UIs exactly when needed, allowing the experience to go beyond simple text and adapters.

One thing is sure: there will be more and more agentic features, and A2UI will be a great bridge between agent power and user needs.

![Building with A2UI: Extending the Expressiveness of AI Agent Interfaces](/static/img/articles/building-with-a2ui-extending-the-expressiveness-of-ai-agent-interfaces/05.webp)
