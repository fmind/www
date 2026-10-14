+++
title = "Da2a: The Future of Data Platforms is Agentic, Distributed, and Collaborative"
description = "For decades, the story of data platforms has been one of centralization and heavy engineering."
date = "2025-09-27"
tags = ["Agent", "Cloud"]
slug = "da2a-the-future-of-data-platforms-is-agentic-distributed-and-collaborative"
syndicated = "https://medium.com/@fmind/da2a-the-future-of-data-platforms-is-agentic-distributed-and-collaborative-741d5aa96fc4"
draft = false
+++

For decades, the story of data platforms has been one of centralization and heavy engineering. We built massive data warehouses and data lakes, but accessing their insights required deep technical expertise. Business users couldn’t simply ask questions; they had to navigate a complex process involving specialized data engineers to build painstaking ETL pipelines, optimized queries, and specific dashboards. This highly technical approach created a rigid, monolithic source of truth that, while powerful, was slow to adapt and created significant bottlenecks. It left decision-makers waiting days or even weeks for answers, completely dependent on an over-burdened engineering team.

![Illustration of the complexity of data platforms (Source: Gemini App)](/static/img/articles/da2a-the-future-of-data-platforms-is-agentic-distributed-and-collaborative/cover.webp)

Illustration of the complexity of data platforms (Source: Gemini App)

What if we flipped the model on its head?

Instead of a single, all-knowing monolith, imagine a collaborative ecosystem where domain experts describe their data in natural language, providing context that empowers a network of intelligent, autonomous agents. Each agent becomes an expert in its domain — sales, marketing, logistics, finance — managing its own data by combining human-provided descriptions with its own skills to answer questions. This is the future of data platforms: a system that is **agentic, distributed, and truly collaborative**.

I created a new open-source project, [**Da2a**](https://github.com/fmind/da2a), to explore this paradigm. It’s a prototype that demonstrates how a multi-agent system can tackle complex data analysis by working together.

### The Old Way vs. The New Paradigm

**The traditional data platform is** **engineering-focused**. The primary challenge is moving, storing, and modeling data. Answering a simple business question like, _“What’s the ROI on our latest social media campaign?”_ could involve:

1. Filing a ticket with the data engineering team.
2. Waiting for them to build a new pipeline to join marketing spend data with sales data.
3. Having an analyst write a complex SQL query across multiple massive tables.
4. Finally, getting a report back, hoping the initial question hasn’t become irrelevant.

**The agentic approach is** **insight-focused**. Instead of a centralized database, you have specialized agents. For instance, the **Marketing Agent** knows everything about campaign spending and lead acquisition. On the other hand, the **E-commerce Agent** is an expert on orders, products, and revenue.

To answer that same question, you simply ask a root “Orchestrator Agent.” The orchestrator understands the goal, formulates a plan, and collaborates with the specialist agents to get the answer. The focus shifts from the _how_ (engineering) to the _what_ (the business question).

### Meet Da2a: An Agentic Platform in Action

Da2a implements this vision with a root orchestrator and two specialized agents: one for an **e-commerce** dataset and another for a **marketing** dataset, both based on real-world data from the [Olist store in Brazil](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

**GitHub Repository:** [https://github.com/fmind/da2a](https://github.com/fmind/da2a "null")

You can ask the e-commerce agent, “How many orders were placed in São Paulo?” or the marketing agent, “What were our top lead sources last year?”. Better yet, you can ask the root orchestrator a question that requires both, like, _“What is the total sales revenue from sellers who were acquired via ‘Display’ advertising?”_

![Screenshot of the Da2a User Interface](/static/img/articles/da2a-the-future-of-data-platforms-is-agentic-distributed-and-collaborative/02.webp)

Screenshot of the Da2a User Interface

The root agent intelligently delegates the work: first asking the marketing agent to identify the sellers from the ‘Display’ channel, then passing that list to the e-commerce agent to calculate their total sales.

### The Architecture: Collaboration via the A2A Protocol

The magic that makes this collaboration possible is the [**Agent-to-Agent (A2A) protocol**](https://a2a-protocol.org/latest/). A2A provides a standardized way for agents to communicate their capabilities and call upon each other’s skills over a network.

![Architecture of the Da2a Application, with Marketing and E-Commerce agents collaborating with the Root Agent](/static/img/articles/da2a-the-future-of-data-platforms-is-agentic-distributed-and-collaborative/03.webp)

Architecture of the Da2a Application, with Marketing and E-Commerce agents collaborating with the Root Agent

The architecture consists of:

1. [**A Root Agent**](https://github.com/fmind/da2a/tree/main/da2a) **:** The orchestrator that receives user requests, plans the execution, and delegates tasks.
2. **Domain Agents:** The [`ecommerce_agent`](https://github.com/fmind/da2a/tree/main/ecommerce) and [`marketing_agent`](https://github.com/fmind/da2a/tree/main/marketing), each running as an independent service with its own database.
3. [**Agent Cards**](https://a2a-protocol.org/latest/tutorials/python/3-agent-skills-and-card/) **:** Each domain agent exposes a JSON “agent card” that acts like a digital business card, describing its name, capabilities, and how to communicate with it.

The root agent is configured to know about these remote agents. Here is a simplified look at the code from the da2a [`agent.py`](https://github.com/fmind/da2a/blob/main/da2a/agent.py) file, which sets up the connection to the remote agents using their "agent cards."

```python
import google.adk.agents.remote_a2a_agent as a2a
import google.adk.tools.agent_tool as at

# The URL points to the 'agent card' of the remote agent
AGENT_CARD_ECOMMERCE = "[https://da2a-ecommerce.fmind.dev/a2a/ecommerce/.well-known/agent-card.json](https://da2a-ecommerce.fmind.dev/a2a/ecommerce/.well-known/agent-card.json)"
AGENT_CARD_MARKETING = "[https://da2a-marketing.fmind.dev/a2a/marketing/.well-known/agent-card.json](https://da2a-marketing.fmind.dev/a2a/marketing/.well-known/agent-card.json)"

# Create local proxy objects for the remote agents
ecommerce_agent = a2a.RemoteA2aAgent(
    name="ecommerce_agent",
    agent_card=AGENT_CARD_ECOMMERCE,
    description="Answers questions about e-commerce data..."
)
marketing_agent = a2a.RemoteA2aAgent(
    name="marketing_agent",
    agent_card=AGENT_CARD_MARKETING,
    description="Answers questions about marketing data..."
)

# The root agent uses these agents as 'tools' to solve problems
root_agent = LlmAgent(
    ...
    tools=[at.AgentTool(ecommerce_agent), at.AgentTool(marketing_agent)],
    ...
)
```

Each domain agent is served via the [Agent Development Kit’s](https://google.github.io/adk-docs/) (ADK) web server, which automatically exposes the A2A endpoints and the agent card.

```bash
# Command to serve an agent and enable A2A communication
adk web --a2a
```

This simple, powerful mechanism allows us to build a distributed system where components can be developed, deployed, and scaled independently.

### The Benefits of Thinking Agentically

This approach unlocks several powerful advantages:

- **Human-Like Task Handling:** Agents can tackle complex, multi-step tasks that require synthesizing information from different domains, much like a human analyst would.
- **Scalability and Extensibility:** Adding a new data domain is as simple as building and deploying a new agent. No need to re-architect the entire platform. The system grows organically.
- **Focus on High-Level Value:** It abstracts the underlying engineering complexity. Data consumers and developers can focus on defining business logic and asking high-level questions, not on writing SQL or managing data pipelines.
- **Autonomous and Collaborative:** Each agent is a valuable tool on its own, but their true power is unlocked when they collaborate through an orchestrator to solve problems that no single agent could handle alone.

### The Road Ahead: Limitations and Future Work

Da2a is a prototype, and building an industrial-grade agentic data platform requires solving some interesting challenges:

1. **Efficient Data Transfer:** A2A is excellent for orchestrating tasks and passing small payloads of text or JSON. It is not designed for transferring gigabytes of data between agents. For that, we’d need to integrate mechanisms that point agents to shared data storage.
2. **Dynamic Agent Discovery:** Currently, the root agent’s knowledge of other agents is hardcoded. A production system would need a discovery service or a registry where agents can dynamically register themselves and their skills.
3. **Memory and Learning:** The agents in this prototype are stateless. The next frontier is to give them memory, allowing them to learn from past interactions, recall previous results, and improve their planning and execution over time.

### Conclusion: A New Frontier for Data

The agentic paradigm represents a fundamental shift in how we think about data architecture. We are moving from rigid, centralized systems to dynamic, decentralized ecosystems of intelligent specialists. This approach promises to create data platforms that are more flexible, more powerful, and more aligned with the way businesses actually work.

There is still much to build, but the potential is immense. The future of data isn’t just about bigger databases or faster queries; it’s about collaboration, intelligence, and a network of agents working together to turn data into insight.

![The future is with Agentic Data Platforms (Source: Gemini App)](/static/img/articles/da2a-the-future-of-data-platforms-is-agentic-distributed-and-collaborative/04.webp)

The future is with Agentic Data Platforms (Source: Gemini App)
