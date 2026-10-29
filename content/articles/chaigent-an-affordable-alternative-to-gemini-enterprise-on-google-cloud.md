+++
title = "Chaigent: An affordable alternative to Gemini Enterprise on Google Cloud"
description = "Build a cost-effective, private AI Agent solution on Google Cloud using Chainlit and Vertex AI. Detailed architecture and code guide."
date = "2026-02-06"
tags = ["Agent", "Cloud", "Project"]
slug = "chaigent-an-affordable-alternative-to-gemini-enterprise-on-google-cloud"
syndicated = "https://medium.com/@fmind/chaigent-an-affordable-alternative-to-gemini-enterprise-on-google-cloud-292c8de08478"
draft = false
+++

The era of simple chatbots is over. Companies are now racing to build [**AI Agent platforms**](https://www.fmind.dev/articles/architecting-the-ai-agent-platform-a-definitive-guide/) — systems that don’t just talk, but _act_. Whether it’s a support bot resolving Jira tickets or a data analyst agent querying BigQuery, these new digital teammates need a platform that offers more than just text generation: they require reasoning, security, and enterprise-grade observability.

[**Gemini Enterprise**](https://cloud.google.com/gemini/enterprise) provides a great path to achieving this on [**Google Cloud**](https://cloud.google.com/). It offers a comprehensive set of features including agent exposition, governance, integrated knowledge search, and a visual agent builder, connecting with backends like [**Vertex AI Agent Engine**](https://cloud.google.com/products/agent-engine), [**Conversational Agent**](https://docs.cloud.google.com/dialogflow/cx/docs), or [**A2A**](https://a2aprotocol.ai/).

However, for some organizations or specific use cases, the cost can be a friction point. The catalog price sits at **~\$7/user/month** for agent users and **~\$35/user/month** for visual agent builders. While this pricing is competitive for knowledge workers who gain significant productivity, it can be prohibitive for large audiences with lower usage frequency, such as field workers or occasional users.

**Enter Chaigent:** [**https://github.com/fmind/chaigent**](https://github.com/fmind/chaigent) **.**

![Chaigent is an affordable alternative to Gemini Enterprise (Source: Gemini App)](/static/img/articles/chaigent-an-affordable-alternative-to-gemini-enterprise-on-google-cloud/cover.webp)

Chaigent is an affordable alternative to Gemini Enterprise (Source: Gemini App)

In this article, I present “Chaigent” ([**Chainlit**](https://chainlit.io/) + Agent), a cost-effective, DIY alternative to Gemini Enterprise on Google Cloud. It leverages the same powerful underlying reasoning engine but replaces the managed frontend with an open-source framework, giving you control over features and costs.

### The Architecture

Chaigent enables you to build a private, secure AI agent platform by combining serverless infrastructure with open-source tooling.

![Architecture of Chaigent (Source: Fmind.dev)](/static/img/articles/chaigent-an-affordable-alternative-to-gemini-enterprise-on-google-cloud/02.webp)

Architecture of Chaigent (Source: Fmind.dev)

The architecture consists of three main layers:

1. **Frontend (** [**Chainlit**](https://chainlit.io/) **on** [**Cloud Run**](https://cloud.google.com/run) **)**: A Python-based UI that handles user sessions, chat history, and authentication.
2. **Backend (** [**Vertex AI Agent Engine**](https://cloud.google.com/products/agent-engine) **)**: The “brain” of the operation, capable of reasoning and tool use.
3. **Persistence & Auth**: [**Cloud SQL**](https://cloud.google.com/sql) for storing chat history and feedback, and [**OAuth**](https://oauth.net/2/) (Google, GitHub, etc.) for secure identity management.

This approach allows you to pay for **consumption only** (Cloud Run CPU + Vertex AI tokens), significantly reducing costs for intermittent usage patterns compared to a flat per-seat license.

### The “Do It Yourself” Trade-off

Gemini Enterprise provides a managed, “batteries-included” platform with built-in governance and visual tools. Chaigent, in contrast, offers a code-first, developer-centric approach.

**What you gain:**

- **Cost Efficiency**: No monthly per-seat licensing fees.
- **Full Customization**: You own the code. Want to add a custom feedback mechanism or a specific UI widget? You can.
- **Platform Independence**: Using [**Chainlit**](https://chainlit.io/) (frontend) and [**Google ADK**](https://google.github.io/adk-docs/) (backend) logic keeps you flexible.

**What you lose (The “Subtext”):**

- **No Visual Builder**: You define agents in code, not a drag-and-drop UI.
- **Manual Governance**: You must implement your own permission logic per agent.
- **Ops Overhead**: You are responsible for deploying, securing, and updating the application.
- **Enterprise Features**: Advanced features like Model Armor ([**Prompt Security**](https://cloud.google.com/security/products/model-armor)) and integrated Knowledge Search ([**RAG**](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-overview)) require manual implementation.

### Implementation Highlights

Chaigent is surprisingly simple to set up. Here is a glimpse of the code.

### 1. Defining the Agent

The agent is defined declaratively using the [**Google ADK**](https://github.com/google/adk-python). It’s just a Python object specifying the model and tools.

```python
# chaigent/agent.py
root_agent = agent(
    name="chaigent",
    model="gemini-2.5-flash",
    description="answer questions with google search.",
    instruction="you are an expert researcher. you always stick to the facts.",
    tools=[google_search],
)
```

### 2. The Bridge (Chainlit Adapter)

The `app.py` acts as the bridge. It connects the user’s chat session to the Vertex AI Agent Engine, handling the streaming response seamlessly.

```python
# app.py

@cl.on_message
async def on_message(message: cl.Message):
    # Initialize response message
    answer = cl.Message(content="")
    await answer.send()

    # Retrieve session
    session = cl.user_session.get("session")
    user_id, session_id = session["userId"], session["id"]

    # Stream the query to Vertex AI
    response_stream = engine.async_stream_query(
        user_id=user_id, message=message.content, session_id=session_id
    )

    # Stream back the tokens
    async for chunk in response_stream:
        for part in chunk.get("content", {}).get("parts", []):
            text = part.get("text", "")
            if text:
                await answer.stream_token(text)
                await answer.update()
```

### User Experience

Despite being a “DIY” solution, the user experience is premium. Chainlit provides features that users expect from modern chat apps.

**Rich Chat Interface**: Supports markdown, code highlighting, and streaming responses out of the box.

![Chat interface of Chaigent](/static/img/articles/chaigent-an-affordable-alternative-to-gemini-enterprise-on-google-cloud/03.webp)

Chat interface of Chaigent

**Authentication & Persistence**: Secure login screens and persisted chat history allow users to resume conversations across devices.

![Login screen of Chaigent](/static/img/articles/chaigent-an-affordable-alternative-to-gemini-enterprise-on-google-cloud/04.webp)

Login screen of Chaigent

**Data Layer**: All interactions are stored in your own SQL database, giving you full ownership of the data for analytics or fine-tuning later.

![Home screen of Chaigent](/static/img/articles/chaigent-an-affordable-alternative-to-gemini-enterprise-on-google-cloud/05.webp)

Home screen of Chaigent

### Conclusion

Chaigent is an excellent solution when **cost efficiency** is the primary driver, particularly for large audiences with low individual usage.

The decision comes down to ROI. At ~\$7/month/user for Gemini Enterprise, you need to save each user at least one hour of work per month to break even. For knowledge workers, this is a no-brainer. But for field workers or casual users, a consumption-based “Pay-as-you-go” model like Chaigent might be the smarter financial move.

If you are ready to trade some convenience for control and cost savings, go build your own agents!

![Source: Gemini App](/static/img/articles/chaigent-an-affordable-alternative-to-gemini-enterprise-on-google-cloud/06.webp)

Source: Gemini App
