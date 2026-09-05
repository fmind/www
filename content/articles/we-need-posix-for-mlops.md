+++
title = "We need POSIX for MLOps"
description = "There is an ever-growing landscape of tools and solutions for MLOps. In this article, I propose a solution to address this challenge."
date = "2023-04-17"
tags = ["MLOps"]
slug = "we-need-posix-for-mlops"
syndicated = "https://medium.com/@fmind/we-need-posix-for-mlops-e7bea8d8ec29"
draft = false
+++

If you work on MLOps, you must navigate [an ever-growing landscape of tools and solutions](https://mattturck.com/mad2023/). This is both an intense source of [stimulation](https://mlops.community/) and [fatigue](https://dshersh.medium.com/too-many-mlops-tools-c590430ba81b) for MLOps practitioners.

![Machine Learning, Artificial Intelligence & Data Landscape — MAD 2023](/static/img/articles/we-need-posix-for-mlops/cover.webp)

[Machine Learning, Artificial Intelligence & Data Landscape — MAD 2023](https://mattturck.com/mad2023/)

Vendors and users face the same problem: **How can we combine all these tools without the** [**combinatorial complexity**](https://en.wikipedia.org/wiki/Combinatorial_explosion) **of** [**creating custom integrations**](https://zenml.io/integrations) **?**

```python
import math
# number of AI/ML tools -> number of possible integrations
print({n: math.comb(n, 2) for n in range(10, 100+10, 10)})
{10: 45, 20: 190, 30: 435, 40: 780, 50: 1225, 60: 1770,
 70: 2415, 80: 3160, 90: 4005, 100: 4950}
```

In this article, I propose a solution analogous to [POSIX](https://en.wikipedia.org/wiki/POSIX) to address this challenge. First, I motivate the creation of common protocols and schemas for combining MLOps tools. Second, I present a high-level architecture to support implementation. Third, I conclude with the benefits and limitations of standardizing MLOps.

### What is POSIX?

[POSIX](https://en.wikipedia.org/wiki/POSIX) (Portable Operating System Interface**)** is a set of standards specified by the [IEEE](https://www.ieee.org/) for defining a level of compatibility between operating systems (e.g., Linux, MacOS, BSD, …).

More concretely, [**POSIX**](https://en.wikipedia.org/wiki/POSIX) **is the foundation that allows end users to implement new applications and ensure they can communicate with each other**. This can be done with shell [commands](https://en.wikipedia.org/wiki/List_of_Unix_commands) (e.g., `ls`, `df`, `pwd`, …) and [pipelines](https://en.wikipedia.org/wiki/Pipeline_%28Unix%29) (e.g., `fd | sort | unique`), or with more complex interfaces such as [network sockets](https://en.wikipedia.org/wiki/Network_socket).

POSIX is also linked with the [Unix Philosophy](https://en.wikipedia.org/wiki/Unix_philosophy), an approach that favors [composability](https://en.wikipedia.org/wiki/Composability "Composability") over [monolithic design](https://en.wikipedia.org/wiki/Monolithic_application "Monolithic application"). To quote [Doug McIlroy](https://en.wikipedia.org/wiki/Douglas_McIlroy) (1978):

1. Make each program do one thing well. To do a new job, build afresh rather than complicate old programs by adding new “features”.
2. Expect the output of every program to become the input to another, as a yet unknown, program. Don’t clutter the output with extraneous information. Avoid stringently columnar or binary input formats. Don’t insist on interactive input.
3. Design and build software, even operating systems, to be tried early, ideally within weeks. Don’t hesitate to throw away the clumsy parts and rebuild them.
4. Use tools in preference to unskilled help to lighten a programming task, even if you have to detour to build the tools and expect to throw some of them out after you’ve finished using them.

### Why do we need POSIX for MLOps?

As ML Engineers we have 2 possibilities for implementing an AI/ML solution: either [go all-in on a set of tools](https://en.wikipedia.org/wiki/Monolithic_application) or [create interfaces to combine, remove, and replace tools](https://en.wikipedia.org/wiki/Software_design_pattern) that are part of the solution.

Going all-in is often the easier way to go. For instance, we can start a new project with [MLflow](https://mlflow.org/) for experiment tracking, [TensorFlow](https://www.tensorflow.org/) as our ML framework, and [Great Expectations](https://greatexpectations.io/) to validate our data. But wait, now the team wants to switch to [Neptune](https://support.neptune.ai/en/articles/13925165-service-shutdown-overview), [PyTorch Lightning](https://pytorch-lightning.readthedocs.io/), and [Evidently](https://www.evidentlyai.com/) … That's a lot of rewrite and rework!

[Our goal as an engineer is to create abstractions](https://en.wikipedia.org/wiki/Abstraction_%28computer_science%29) and [protocols](https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview) to avoid such hassle. On the web, we can use any web browser (e.g., Chrome, Firefox, Edge), with any web server (e.g., NGINX, Apache, Gunicorn) without any rewrite or custom integration. If something wants to create a new web program, this entity can do it without asking for permission or requiring changes from other actors.

[**AI/ML is a complex field where new solutions are constantly added to solve an increasing number of user cases**](https://paperswithcode.com/) **. We should not limit nor slow the growth of AI/ML because of inconvenient software design.**

### How should we implement it?

My proposal is to massively leverage [message brokers](https://en.wikipedia.org/wiki/Message_broker) like [Apache Kafka](https://kafka.apache.org/), [Redis](https://redis.com/solutions/use-cases/messaging), or [ZeroMQ](https://zeromq.org/) to exchange metadata and instructions between AI/ML components. The main benefit of message brokers is to minimize the mutual awareness between components and decouple information sharing between producers and consumers. As [Rich Hickey](https://en.wikipedia.org/wiki/Rich_Hickey) explained, this kind of architecture supports the emergence of a [Language of the System](https://www.youtube.com/watch?v=ROor6_NGIWU). This is also [the paradigm behind the design of the Erlang language](https://www.erlang.org/blog/message-passing/).

For MLOps, this means separating each component such as Experiment Tracker, Model Training, or Pipeline Monitoring (e.g., using [Python module](https://docs.python.org/3/tutorial/modules.html) or [Docker container](https://www.docker.com/resources/what-container/)), and exchanging information only through message brokers. This design seeks to implement the [SOLID principles](https://en.wikipedia.org/wiki/SOLID):

- [**S**ingle-responsibility principle](https://en.wikipedia.org/wiki/Single-responsibility_principle "Single-responsibility principle"): “There should never be more than one reason for a [class](https://en.wikipedia.org/wiki/Class_%28computer_programming%29 "Class (computer programming)") to change.”
- The [**O**pen–closed principle](https://en.wikipedia.org/wiki/Open%E2%80%93closed_principle "Open–closed principle"): “Software entities should be open for extension, but closed for modification.”
- The [**L**iskov substitution principle](https://en.wikipedia.org/wiki/Liskov_substitution_principle "Liskov substitution principle"): “Functions that use pointers or references to base classes must be able to use objects of derived classes without knowing it.”
- The [**I**nterface segregation principle](https://en.wikipedia.org/wiki/Interface_segregation_principle "Interface segregation principle"): “Clients should not be forced to depend upon interfaces that they do not use.”
- The [**D**ependency inversion principle](https://en.wikipedia.org/wiki/Dependency_inversion_principle "Dependency inversion principle"): “Depend upon abstractions, \[not\] concretions.”

![High-level architecture: decoupling between an ML Pipeline and MLOps components](/static/img/articles/we-need-posix-for-mlops/02.webp)

High-level architecture: decoupling between an ML Pipeline and MLOps components

Each MLOps component should work like a [micro-service](https://en.wikipedia.org/wiki/Microservices). When the component receives an instruction (e.g., log a parameter, get the location of a model, …), it should reply to the sending process with the information requested. A message can [be dispatched to several components](https://cloud.google.com/pubsub/docs/overview) (i.e., fan out), and the component can acknowledge that the message has been processed with a status or error message. The components should be as [loosely coupled](https://en.wikipedia.org/wiki/Loose_coupling) as possible, and they must be configured with a [creational pattern](https://en.wikipedia.org/wiki/Creational_pattern) to swap the components with soft code (e.g., configuration files).

In addition, [common schemas](https://schema.org/) (i.e., [names for things](https://en.wikipedia.org/wiki/Ontology_%28computer_science%29)) are required to enable global integrations between MLOps tools. The main benefit of [POSIX](https://en.wikipedia.org/wiki/POSIX) is not only to provide design concepts (e.g., [file descriptors](https://en.wikipedia.org/wiki/File_descriptor)), but also standard names to facilitate the collaboration between actors (e.g., /dev/std{in,err,out} for [standard streams](https://en.wikipedia.org/wiki/Standard_streams)).

### Conclusions

MLOps is a complex field and we should not make this field even more complex through [accidental complexity](https://wiki.c2.com/?AccidentalComplexity). MLOps actors need to facilitate the interoperability of the tools we build so we can focus on the real problems: deliver value to our organizations. The high-level architecture proposed in this article is an attempt to answer this problem through common protocols and standard naming.

However, there is a hard truth I acknowledge: nobody got rich or famous from creating a standard. While this contribution would be beneficial for all MLOps actors, no individual has the incentive to create this initiative on its own. The alternative is to wait for [Darwinism](https://en.wikipedia.org/wiki/Darwinism) to cull the MLOps tools available, but I'm not sure [the best solutions will emerge from this process](https://en.wikipedia.org/wiki/Worse_is_better).

Finally, there is also another thing you need to know about standards. But I think XKCD does a better job than me at explaining it 😄.

![Standards — https://xkcd.com/927/](/static/img/articles/we-need-posix-for-mlops/03.webp)

Standards — [https://xkcd.com/927/](https://xkcd.com/927/)
