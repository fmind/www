+++
title = "CAG vs. RAG: Choosing the Right Strategy for Your AI Application"
description = "CAG vs RAG for Generative AI: Compare latency, cost \u0026 complexity. Choose the best LLM context strategy for your app."
cover_alt = "Black and white photo of a man in a deerstalker hat peering through a magnifying glass"
date = "2025-04-23"
tags = ["LLM", "RAG"]
slug = "cag-vs-rag-choosing-the-right-strategy-for-your-ai-application"
draft = false
+++

As AI Engineers, we constantly seek the most effective ways to provide Large Language Models (LLMs) with the right context to answer questions or perform tasks accurately. Two prominent techniques have emerged: [Context Augmented Generation](https://www.anthropic.com/news/contextual-retrieval) (CAG) and [Retrieval Augmented Generation](https://en.wikipedia.org/wiki/Retrieval-augmented_generation) (RAG). But how do they stack up, especially regarding performance and cost? And when should you choose one over the other?

**In this article, we’ll break down the key differences between CAG and RAG, focusing on two critical aspects: latency and price**. We’ll explore findings from a practical benchmark to understand the trade-offs, discuss the often-overlooked factor of implementation complexity, and provide recommendations to help you decide which approach best suits your specific needs, whether you’re building a quick prototype or optimizing a production system.

![Black-and-white portrait of a man in a deerstalker hat peering through a magnifying glass — Photo by Andres Siimon on Unsplash](/static/img/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/cover.webp)

Black-and-white portrait of a man in a deerstalker hat peering through a magnifying glass — Photo by [Andres Siimon](https://unsplash.com/@johnmcclane) on [Unsplash](https://unsplash.com)

### 🥊The Contenders: CAG and RAG Explained

**Context Augmented Generation (CAG):** This approach involves directly injecting the relevant context into the LLM prompt. For large contexts, this can be inefficient. However, modern platforms like [Google’s Gemini](https://ai.google.dev/gemini-api/docs/models) API offer [caching mechanisms](https://ai.google.dev/gemini-api/docs/caching). This allows you to pre-process and cache [large contexts](https://ai.google.dev/gemini-api/docs/long-context), sending only the cache identifier and the query in subsequent requests, significantly reducing the input tokens processed per call after the initial caching.

```python
# cache creation
cache = genai_client.caches.create(
    model=GENAI_MODEL,
    config=gt.CreateCachedContentConfig(
        display_name=CACHE_NAME,
        contents=[content],
        ttl=CACHE_TTL,
    )
)
# cache retrieval
response = genai_client.models.generate_content(
  model=GENAI_MODEL,
  contents=query,
  config=gt.GenerateContentConfig(
      cached_content=CACHE_NAME,
  ),
)
```

**Retrieval Augmented Generation (RAG):** Instead of sending the entire context, RAG first retrieves the most relevant snippets or chunks of information from a larger knowledge base (often stored in a vector database like [ChromaDB](https://www.trychroma.com/), [Vertex AI Search](https://cloud.google.com/enterprise-search?hl=en), or [Cloud SQL](https://cloud.google.com/sql)) using techniques like [semantic search](https://cloud.google.com/discover/what-is-semantic-search). Then, relevant chunks are added to the prompt alongside the user’s query.

```python
# database ingestion
database_client = cdb.PersistentClient()
collection = database_client.create_collection(name=COLLECTION_NAME, embedding_function=EMBEDDING_FUNCTION)
collection.add(ids=ids, documents=docs)
# database retrieval
docs = collection.query(
    include=["documents"],
    query_texts=[query],
    n_results=5,
)['documents'][0]
response = genai_client.models.generate_content(
    model=GENAI_MODEL,
    contents=docs + [query],
)
```

### ⏱ Performance Showdown: Latency

Latency, the time it takes to get a response, is crucial for user experience. Our analysis, using the [new structured Wikipedia data on Kaggle](https://www.kaggle.com/datasets/wikimedia-foundation/wikipedia-structured-contents) and the [`gemini-2.0-flash-001`](https://ai.google.dev/gemini-api/docs/models#gemini-2.0-flash) model, compared three simple scenarios:

- **Base:** Sending the full context with the query every time.
- **CAG:** Using Gemini’s [Context Caching](https://ai.google.dev/gemini-api/docs/caching) feature with full context.
- **RAG:** Retrieving the top 5 relevant chunks from a [ChromaDB](https://www.trychroma.com/) database.

The results are clear (see the linked [Colab Notebook](https://colab.research.google.com/drive/1yt2rHhX9X8dD1v50Sk9_o7hF_5tAt7bH?usp=sharing) for details):

![Latency Comparison: Base vs. CAG vs. RAG](/static/img/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/02.webp)

Latency Comparison: Base vs. CAG vs. RAG

- **Base (full context) was the slowest**, averaging 8.34 seconds, and this latency increased significantly with larger context sizes (moving from 100k to 500k tokens).
- **CAG (with caching) was the next fastest**, averaging around 6.68 seconds. The initial caching takes time, but subsequent calls are faster than the base approach.
- **RAG consistently demonstrated the lowest latency**, averaging around 1.06 seconds in our tests. This is because the LLM only processes a small amount of retrieved text plus the user query.

![Latency Comparison by Context Size (100k vs. 500k input tokens)](/static/img/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/03.webp)

Latency Comparison by Context Size (100k vs. 500k input tokens)

**Key Takeaway:** RAG holds a distinct advantage in latency, especially as the context size grows. CAG with caching offers improvement over naive context stuffing but doesn’t match RAG’s speed.

### 💰 Performance Showdown: Price

Cost is a deciding factor in deploying AI solutions. The [pricing models](https://ai.google.dev/gemini-api/docs/pricing) typically involve costs per input and output token, embedding generation (for RAG), and potentially database/cache storage.

To understand how these costs differ in practice, our comparison looked at various scenarios by tweaking key variables:

- **Approach**: Evaluating the cost of using no Cache (Base), a Cache (CAG), and a Vector Database like Chroma or Cloud SQL (RAG)
- **LLM Used:** Comparing costs between different models (Gemini 2.0 Flash vs. Flash Lite).
- **Daily Request Volume:** Estimating costs based on different usage levels (1,000 vs. 10,000 requests per day).
- **Tokens per Request:** Analyzing the impact of different context sizes or retrieval amounts (e.g., ranging from 5,000 tokens for RAG to 100,000 or 500,000 for CAG).

These variations help illustrate how costs scale depending on the chosen model, usage intensity, and the specific context handling strategy employed.

![Price Comparison with different Models, Approaches, Databases, \# of Requests and \# of Tokens](/static/img/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/04.webp)

Price Comparison with different Models, Approaches, Databases, \# of Requests and \# of Tokens

Based on estimations ([see the linked Google Sheet for details](https://docs.google.com/spreadsheets/d/1WPmoqWB5UUO2tq9-z2ng2t_a6K6fqdzJTLQZxOytP4U/edit?usp=sharing)):

- **RAG tends to be more cost-effective**, particularly when dealing with large underlying datasets. While it incurs costs for embedding generation and vector database hosting, the cost per LLM call is lower because far fewer tokens are processed compared to sending the entire context. For 1,000 daily requests with a 25k token context using RAG (Chroma OSS), the estimated daily cost was ~\$4.11/day.
- **Base (CAG without caching)** becomes expensive quickly as context size increases. Sending a 100k token context for 1,000 daily requests was estimated at ~\$15.34/day, jumping to ~\$75.34/day for a 500k context.
- **CAG (with caching)** significantly mitigates the cost compared to the non-cached version but adds a cache storage cost. For 1,000 daily requests, the 100k cached context cost was estimated at ~\$6.46/day, and the 500k cached context at ~\$31.06/day.

![Price / Request Comparison with different Models, Approaches, Databases, \# of Requests and \# of Tokens](/static/img/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/05.webp)

Price / Request Comparison with different Models, Approaches, Databases, \# of Requests and \# of Tokens

**Key Takeaway:** RAG generally wins on price for large-scale, frequent use cases, especially with very large contexts. CAG _with caching_ can be competitive at smaller context sizes (like 100k tokens in our test) but scales less favourably than RAG as context grows.

### ⚙️ Factoring The Complexity

While RAG might seem like the clear winner technically, it introduces significantly more complexity during development:

- **Implementation:** Setting up a RAG pipeline involves more moving parts: data chunking strategies, choosing and implementing an embedding model, setting up and managing a vector database, and creating the retrieval logic … This is often challenging for a team starting a Gen AI prototype.
- **Tuning:** Optimizing RAG performance requires careful tuning — finding the right chunk size, deciding how many chunks to retrieve (`n_results`), setting similarity thresholds, etc. This takes development time and experimentation. Building a RAG is simple, but building a good RAG is complex.

**CAG, especially using platform features like Gemini’s caching, is often simpler to implement initially.**

### 🎯 The Verdict: When to Use Which?

There’s no single “best” answer; it depends on your specific needs:

**Use CAG (preferably with caching):**

- For **prototypes and MVPs** where speed of development is crucial.
- When dealing with **relatively small context sizes** (e.g., under 100k tokens, where the latency/cost difference might be negligible).
- If the context is **dynamic and changes frequently**, making constant re-indexing for RAG impractical (though caching also needs refreshing).

**Use RAG:**

- When **optimizing for low latency and cost** is a primary goal, especially at scale.
- When dealing with **very large, relatively static knowledge bases** (millions of tokens or more).
- When you need the ability to **cite specific sources** for the generated answer (as retrieval tells you which chunks were used).

**Recommendation:** Always perform a [quick estimation](https://docs.google.com/spreadsheets/d/1WPmoqWB5UUO2tq9-z2ng2t_a6K6fqdzJTLQZxOytP4U/edit?gid=770769719#gid=770769719) of latency and cost for your specific use case and expected load. Start simple (CAG with cache if possible) for initial development and validation. If performance or cost becomes a bottleneck as you scale, invest the time to build and tune a RAG pipeline.

### 🏁 Conclusion

RAG often presents a technically superior solution for handling large contexts in terms of raw latency and cost, particularly at scale. However, this performance comes at the cost of increased implementation complexity.

CAG, especially when augmented with caching, offers a simpler starting point that can be perfectly adequate for many use cases, especially during prototyping or with smaller contexts. Choose wisely based on your project’s specific constraints and goals!

For a deeper dive into the analysis mentioned, check out these resources:

- **Latency Benchmark Notebook:** [Comparison: CAG vs. RAG — Colab](https://colab.research.google.com/drive/1yt2rHhX9X8dD1v50Sk9_o7hF_5tAt7bH)
- **Price Estimation Sheet:** [Comparison: CAG vs. RAG — Ranking](https://docs.google.com/spreadsheets/d/1WPmoqWB5UUO2tq9-z2ng2t_a6K6fqdzJTLQZxOytP4U/edit?usp=sharing)
- **My entry to Kaggle "Gemini Long Context" competition**: [https://docs.google.com/presentation/d/1H7Kq8Ur3f76mknLcugR0ZaBFqtba6foLQS_i7KG_4Sc/edit#slide=id.g315f80125e3_1_48](https://docs.google.com/presentation/d/1H7Kq8Ur3f76mknLcugR0ZaBFqtba6foLQS_i7KG_4Sc/edit#slide=id.g315f80125e3_1_48)

![Observatory domes on a mountaintop under a night sky full of stars and the Milky Way — Photo by Conner Baker on Unsplash](/static/img/articles/cag-vs-rag-choosing-the-right-strategy-for-your-ai-application/06.webp)

Observatory domes on a mountaintop under a night sky full of stars and the Milky Way — Photo by [Conner Baker](https://unsplash.com/@connerbaker) on [Unsplash](https://unsplash.com)
