+++
title = "Introducing GentWriter: Building a Multi-Agent Content Generator with Google’s ADK 👾"
description = "How I built GentWriter with Google's ADK: a multi-agent system that turns one article URL into an SEO description, an X post, and a LinkedIn post."
cover_alt = "Bearded man in a black top hat and waistcoat tipping his hat while leaning on a cane against a dark backdrop"
date = "2025-04-28"
tags = ["Agent", "Python", "Project"]
slug = "introducing-gentwriter-building-a-multi-agent-content-generator-with-googles-adk"
draft = false
+++

In the fast-paced world of content creation, efficiency is key. Manually crafting social media posts for different platforms based on a single piece of content can be time-consuming and repetitive. What if you could automate this process using the power of Generative AI? 🤔 That’s exactly what I set out to do with **GentWriter**, a project exploring the capabilities of [**Google’s Agent Development Kit (ADK)**](https://google.github.io/adk-docs/) for a practical use case: generating social media content through a multi-agent strategy.

In this article, I’ll walk you through how I built GentWriter, showcasing the potential of ADK for creating specialized AI agents. We’ll look at its features, the development experience, and how it leverages a multi-agent system to streamline content creation.

![Bearded gentleman in a top hat and waistcoat tipping his hat while leaning on a cane — Photo by Dmytro Tolokonov on Unsplash](/static/img/articles/introducing-gentwriter-building-a-multi-agent-content-generator-with-googles-adk/cover.webp)

Bearded gentleman in a top hat and waistcoat tipping his hat while leaning on a cane — Photo by [Dmytro Tolokonov](https://unsplash.com/@dtolokonov) on [Unsplash](https://unsplash.com)

### The Challenge: Taming the Social Content Beast 🦁

Keeping multiple social media feeds updated with relevant content derived from a single source (like a blog post or article) requires significant effort. Tailoring the message, tone, and length for each platform (think X vs. SEO vs. LinkedIn) adds another layer of complexity.

![Smartphone home screen with Instagram, Twitter, and LinkedIn app icons — Photo by Nik on Unsplash](/static/img/articles/introducing-gentwriter-building-a-multi-agent-content-generator-with-googles-adk/02.webp)

Smartphone home screen with Instagram, Twitter, and LinkedIn app icons — Photo by [Nik](https://unsplash.com/@helloimnik) on [Unsplash](https://unsplash.com)

### Enter GentWriter: Your AI Content Assistant 🤖

GentWriter tackles this challenge. Its core mission is to take a URL of an article and automatically generate:

- An SEO-friendly meta description 🔍
- A concise and engaging Twitter (X) post 🐦
- A professional LinkedIn post 👔

Example with my latest article: [https://www.fmind.dev/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/](https://www.fmind.dev/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/)

**SEO Description**

> CAG vs RAG for AI: Understand the key differences, latency, price, and complexity to choose the right strategy for your application.

**X Post**

> CAG vs RAG: Which is the best strategy for your \#GenAI app? 🤔 I break down the latency, price, & complexity trade-offs in my latest article! RAG wins for large scale & low latency, but CAG is great for quick prototypes. Check it out! 👇 \#AI \#MLOps [https://www.fmind.dev/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/](https://www.fmind.dev/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/)

**LinkedIn Post**

> Choosing the right strategy for your AI application can be tricky! I recently read an insightful article that dives into the comparison between Context Augmented Generation (CAG) and Retrieval Augmented Generation (RAG), focusing on latency, price, and implementation complexity.

> The article highlights that RAG generally offers lower latency and cost, especially for large-scale applications with substantial knowledge bases. However, CAG, particularly with caching, can be a simpler and more efficient starting point for prototypes or when dealing with smaller context sizes. It emphasizes the importance of evaluating your specific needs and constraints before deciding which approach to use. A key takeaway for me was the reminder to estimate latency and cost for your specific use case before committing to a solution.

> Check out the full article for a deeper dive into the analysis and practical recommendations: [https://www.fmind.dev/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/](https://www.fmind.dev/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/)

> What are your experiences with CAG and RAG? I’m curious to hear your thoughts! \#ArtificialIntelligence \#RAG \#CAG \#GenerativeAI \#LLM \#MLOps

### Under the Hood: Leveraging Google ADK 🛠️

GentWriter is built using [Google’s Agent Development Kit](https://google.github.io/adk-docs/) (ADK), which makes orchestrating multiple AI agents surprisingly simple. Here’s how it works:

1. **Article Retrieval Agent:** This agent fetches the article’s content and title from the provided URL using a dedicated tool (`get_article_from_uri`).
2. **Parallel Processing Power:** A `parallel_writer_agent` then takes over, running three specialized writer agents simultaneously:

- **SEO Writer:** Crafts that crucial, concise meta description.
- **X (Twitter) Writer:** Generates a punchy tweet, complete with hashtags and link, using a specific persona.
- **LinkedIn Writer:** Creates a more detailed, professional post highlighting key insights for a business audience.

![Orchestration of agents included in GentWriter](/static/img/articles/introducing-gentwriter-building-a-multi-agent-content-generator-with-googles-adk/03.webp)

Orchestration of agents included in GentWriter

This combination of sequential steps and parallel processing makes the whole workflow efficient. The use of Pydantic ensures the data passed between agents is well-structured and reliable.

```python
class Article(pdt.BaseModel):
    """Schema of an online article."""

    link: str = pdt.Field(description="The link of the article.")
    title: str = pdt.Field(description="The title of the article.")
    content: str = pdt.Field(description="The content of the article in markdown.")

seo_writer_agent = agents.LlmAgent(
    name="seo_writer_agent",
    model="gemini-2.0-flash",
    description="Generates concise, keyword-focused SEO meta descriptions from article information.",
    instruction=tw.dedent("""
        - **Role:** You are an expert SEO Analyst specializing in crafting compelling meta descriptions.
        - **Task:** Summarize the key information from the provided article content into a concise and informative SEO meta description.
        - **Input:** You will receive the article object containing the link, title, and content.
        - **Constraint:** The description MUST be less than 150 characters.
        - **Objective:** Maximize click-through rate (CTR) from search engine results pages (SERPs). Focus on accuracy, relevance, and incorporating likely search keywords naturally.
        - **Format:** Output only the description text. Do not include labels like "SEO Description:".
    """),
    input_schema=Article,
    output_key="seo_description",
    generate_content_config=gt.GenerateContentConfig(
        temperature=0.3,
        max_output_tokens=100,
    ),
)
```

### Key Features ✨

- **Automated Content Fetching:** Grabs article content and title directly from a URL.
- **Multi-Platform Generation:** Creates tailored content for SEO, Twitter (X), and LinkedIn.
- **Modular Agent Design:** Built with distinct, reusable agents using the `google-adk` framework.
- **Configurable:** Easy to change the underlying Google Generative AI model via environment variables.
- **Developer-Friendly:** Comes with a CLI and a web UI for easy testing and interaction.

![Repository of GentWriter: https://github.com/fmind/gentwriter](/static/img/articles/introducing-gentwriter-building-a-multi-agent-content-generator-with-googles-adk/04.webp)

Repository of GentWriter: [https://github.com/fmind/gentwriter](https://github.com/fmind/gentwriter)

### The Development Journey: Pros & Cons 📊

Working with Google’s ADK on the GentWriter project was a positive experience overall:

**What I Liked (Pros 👍):**

- **Rapid Development:** Went from idea to a working prototype in just a few hours. ADK really speeds things up!
- **Clean Structure:** The SDK keeps things organized and easy to manage.
- **Powerful Features:** Integrations like Vertex AI Search and MCP offer exciting possibilities.
- **Multi-Agent Coordination:** Handling sequential and parallel agent flows is intuitive and supported natively.
- **Reliable Outputs:** Pydantic integration is great for ensuring structured data between workflow steps.
- **Helpful Tooling:** The included CLI and Web UI are fantastic for development and testing!
- **Asynchronous Nature:** Built with async capabilities for better performance.
- **Easy Deployment:** Simple to deploy the agent as an API on Google Cloud Run.

**Minor Hiccups (Cons 👎):**

- **Deployment Flexibility:** While Cloud Run API deployment is smooth, more out-of-the-box options for full web apps or chatbot integrations would be welcome (e.g., Teams, Slack, Google Chat, …).
- **Documentation:** Generally good, but some niche areas (like specifying dependencies for Cloud Run via `requirements.txt`) could benefit from more examples.

### See GentWriter in Action! 👀

Want to try it yourself? I’ve set up a simple web interface:

![Demo of GentWriter](/static/img/articles/introducing-gentwriter-building-a-multi-agent-content-generator-with-googles-adk/05.webp)

Demo of GentWriter

### Final Thoughts ✨

Building GentWriter with Google’s ADK was an insightful experience. It’s a potent framework for developers looking to leverage LLMs in structured, multi-agent applications. While minor improvements could be made, ADK provides a solid, efficient, and enjoyable way to build complex AI solutions.

If you’re automating content workflows or exploring agent-based systems, definitely give ADK a look!

**Links**:

- **GitHub Repository**: [https://github.com/fmind/gentwriter](https://github.com/fmind/gentwriter)
- **ADK Documentation**: [https://google.github.io/adk-docs/](https://google.github.io/adk-docs/)

![LEGO Voltron robot assembled from colored lion robots in a LEGO store, like agents combined into one system — Photo by Parmanand Jagnandan on Unsplash](/static/img/articles/introducing-gentwriter-building-a-multi-agent-content-generator-with-googles-adk/06.webp)

LEGO Voltron robot assembled from colored lion robots in a LEGO store, like agents combined into one system — Photo by [Parmanand Jagnandan](https://unsplash.com/@parmanand) on [Unsplash](https://unsplash.com)
