+++
title = "Is AI/ML Monitoring just Data Engineering? 🤔"
description = "While the future of machine learning and MLOps is being debated, practitioners still need to attend to their machine learning models in…"
date = "2023-07-15"
tags = ["MLOps"]
slug = "is-ai-ml-monitoring-just-data-engineering"
syndicated = "https://medium.com/@fmind/is-ai-ml-monitoring-just-data-engineering-10a2525a9c73"
draft = false
+++

[While the future of machine learning and MLOps is being debated](https://www.youtube.com/watch?v=uejAJSynLJo&t), practitioners still need to attend to their machine learning models in production. This is no easy task, as ML engineers must constantly assess the quality of the data that enters and exits their pipelines, and ensure that their models generate the correct predictions. To assist ML engineers with this challenge, several AI/ML monitoring solutions have been developed.

In the past few weeks, I reviewed several of these AI/ML monitoring solutions for a client. We considered vendor solutions ([Arize](https://arize.ai/), [Superwise](https://superwise.ai/), [Aporia](https://coralogix.com/blog/coralogix-acquires-aporia/)), open-source solutions ([Evidently](https://www.evidentlyai.com/), [Deepchecks](https://deepchecks.com/)), and even building our own solution. These reviews gave me a lot of food for thought about the essence of AI/ML monitoring and how it should fit into an [MLOps lifecycle](https://ml-ops.org/content/mlops-principles#:~:text=As%20machine%20learning%20and%20AI,debt%E2%80%9D%20in%20machine%20learning%20applications.).

![Is AI/ML Monitoring just Data Engineering? 🤔](/static/img/articles/is-ai-ml-monitoring-just-data-engineering/cover.webp)

In this article, I will discuss the nature of AI/ML monitoring and how it relates to data engineering. First, I will present the similarities between AI/ML monitoring and data engineering. Second, I will enumerate additional features that AI/ML monitoring solutions can provide. Third, I will briefly touch on the topic of AI/ML observability and its relation to AI/ML monitoring. Finally, I will provide my conclusion about the field of AI/ML monitoring and how it should be considered to ensure the success of your AI/ML project.

### AI/ML Monitoring is Data Engineering …

There are many similarities between AI/ML monitoring and data engineering. Let’s first look at a simplified AI/ML pipeline in production:

![Example of an AI/ML pipeline in production](/static/img/articles/is-ai-ml-monitoring-just-data-engineering/02.webp)

Example of an AI/ML pipeline in production

We can spot several common points with a data engineering pipeline:

- Each pipeline step ingests and produces data.
- Steps can be chained together (e.g., like a [UNIX pipeline](https://en.wikipedia.org/wiki/Pipeline_%28Unix%29)).
- At the end of the process, it produces alerts, metrics, and dashboards.

We can also spot some differences specific to AI/ML pipelines:

- There is an AI/ML model used at some point.
- … and that’s it!

[**Does the use of an AI/ML model make a big difference in a data pipeline?**](https://mlops.community/mlops-is-mostly-data-engineering/) On the one hand, it is just another step that takes data in and generates data out. On the other hand, AI/ML models require extra attention to properly handle the methodology (e.g., avoiding data leakage), hardware (e.g., using GPUs), and new components (e.g., model registries). As this additional complexity requires a specific set of skills and expertise, I tend to think this difference matters. The best proof is that we need specific engineers to manage these challenges (i.e., ML engineers).

Let’s now explore how this question affects AI/ML monitoring.

### … and it is also more than Data Engineering

The added value of AI/ML monitoring can be summarized in one word: **semantics**. People are much more efficient at dealing with specific concepts than generic ones. To quote this great article from [François Chollet](https://medium.com/u/7462d2319de7) ([User experience design for APIs](https://blog.keras.io/user-experience-design-for-apis.html "Permalink to User experience design for APIs")):

> Like most things, API design is not complicated, it just involves following a few basic rules. They all derive from a founding principle: **you should care about your users.** All of them. Not just the smart ones, not just the experts. Keep the user in focus at all times. Yes, including those befuddled first-time users with limited context and little patience. **Every design decision should be made with the user in mind.**

For example, in neural networks, we can use user-friendly concepts such as “layers”, “dropout”, and “pooling” instead of more general terms like “operations”, “filters”, and “aggregations”. Similarly, for AI/ML monitoring, we can adapt the UI and API to deal with concepts like “segments”, “baselines”, and “environments”. The underlying techniques can be found in every data engineering pipeline, but the user experience has been tailored to focus users on their use cases and help them become more productive.

![Semantic related to Deep Neural Networks](/static/img/articles/is-ai-ml-monitoring-just-data-engineering/03.webp)

Semantic related to Deep Neural Networks

**This raises the question of whether this additional semantic value is valuable for data scientists and ML engineers**. I believe that it is. [Naming things](https://www.karlton.org/2017/12/naming-things-hard/) (i.e., coming up with the semantics) is hard, and [humans tend to be lazy](https://en.wikipedia.org/wiki/Thinking,_Fast_and_Slow) (i.e., systems 1 and 2). [Our main struggle is always to structure the solution and find the best abstractions to empower developers without adding too much complexity](https://www.youtube.com/watch?v=SxdOUGdseq4). Therefore, it is best to let experts in the field think of the best solutions, just as most web developers do when they use [a framework written by specialists in this domain](https://www.djangoproject.com/).

Let’s now review how the authors of AI/ML monitoring solutions can help.

### My opinion on AI/ML monitoring solutions

All the AI/ML monitoring solutions I tested have nailed the core workflow: data ingestion, metric computation, alert notification, and error visualization. While they all have their strengths and weaknesses, I can see how each of these solutions can bring value to end users and help them get started with better tools and practices.

However, I found a major flaw with most vendor-based solutions: **they do not allow metrics to be exported to other systems**. This is problematic for two reasons. First, users cannot leverage vendor solutions to support custom use cases (e.g., to expose metrics to the business or optimize the training of their models). This means that ML engineers either have to adopt the vendor’s solution entirely and stick with it, or recreate custom pipelines to meet their other needs. Second, most vendors reimplement existing components instead of leveraging the ones developed by other vendors. For instance, I would rather use Tableau for visualization and Datadog for alerting than the tools provided by AI/ML monitoring vendors. AI/ML monitoring vendors cannot catch up to the years of development and dedication that other data vendors have put into their products.

I do not blame AI/ML monitoring vendors for this. [It is challenging to create all of these integrations as there is no common protocol for MLOps systems](https://mlops.community/we-need-posix-for-mlops/). We have HTTP, SMTP, and TCP/IP as a universal bridge for the internet, but we do not have anything similar for MLOps. As a result, ML engineers are left with only two options: (1) hope that the vendors will fulfill all of their use cases now and in the future, or (2) build their own solution and focus on the interoperability of their platform. Based on your profile (i.e., end-user vs. engineer), you might choose one over the other.

![Photo by Mike Erskine on Unsplash](/static/img/articles/is-ai-ml-monitoring-just-data-engineering/04.webp)

Photo by [Mike Erskine](https://unsplash.com/@mikejerskine?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

### A note on AI/ML Observability

Recently, [we had an interesting discussion about AI/ML monitoring and observability in the MLOps community](https://mlops-community.slack.com/archives/C015J2Y9RLM/p1689069088728459). [Raphaël Hoogvliets](https://medium.com/u/2ec3b8d15687) even wrote [a great article that summarizes these concepts](https://medium.com/@hoogvliets/fff574a8974f). In short, AI/ML monitoring refers to the ability to monitor individual components (e.g., which error occurred, where, and when), while AI/ML observability provides a holistic and high-level overview of the entire system (e.g., why the error occurred and what caused it).

Many AI/ML monitoring vendors advertise themselves as “AI/ML observability solutions.” However, I believe this is overstated, as most of their solutions only look at individual models and consider only their inputs and outputs. They do not monitor the entire data pipeline (e.g., the first dataset used), nor are they able to relate the events that occur during its operation (e.g., a new column was added by another team).

As a result, it is up to the ML engineer to provide these AI/ML observability capabilities across the entire pipeline. ML engineers can use a lineage system (e.g., [OpenLineage](https://openlineage.io/)) or implement an [Event-Driven Architecture](https://en.wikipedia.org/wiki/Event-driven_architecture) (EDA) to trace the high-level signals that are triggered throughout the pipeline’s lifetime. [Data contracts](https://dataproducts.substack.com/p/the-rise-of-data-contracts) can also be used to define what is “normal” and what is not. I believe this is a promising area of research that has the potential to improve the maturity of MLOps platforms.

![The Pyramid of Monitoring for AI/ML Solutions](/static/img/articles/is-ai-ml-monitoring-just-data-engineering/05.webp)

The Pyramid of Monitoring for AI/ML Solutions

### Conclusions

**AI/ML monitoring can be seen as a superset of data engineering, but it should not be treated as a subset**. In this way, AI/ML monitoring solutions can help bridge the gap between data toolkits and MLOps use cases, as long as they do not remove the ability to integrate their metrics with other systems. While the temptation and constraints to adopt the best solutions on the market can be high, I encourage you to consider whether the value proposition meets both your needs AND your software principles.

To conclude this article, I would like to refer to one of my favorite books: [Gödel, Escher, Bach](https://en.wikipedia.org/wiki/G%C3%B6del,_Escher,_Bach) by [Douglas R. Hofstadter](https://en.wikipedia.org/wiki/Douglas_Hofstadter). I love how the author describes the never-ending loop that arises when systems remain as open as possible, even to themselves. For example, DNA creates proteins that can change or manage DNA, and a program can take instructions to create another program (i.e., a compiler). I find similarities in data and AI/ML pipelines, and I would be fascinated by an MLOps process that could create a model capable of managing MLOps processes. We should strive to focus on the [composability](https://en.wikipedia.org/wiki/Composability) and [interoperability](https://en.wikipedia.org/wiki/Interoperability) of our systems, as we never know what may come next.

![Cover of Gödel, Escher, Bach by Douglas R. Hofstadter](/static/img/articles/is-ai-ml-monitoring-just-data-engineering/06.webp)

Cover of Gödel, Escher, Bach by Douglas R. Hofstadter
