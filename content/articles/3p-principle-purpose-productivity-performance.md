+++
title = "3P Principle: Purpose, Productivity, Performance"
description = "A fundamental trade-off that affects the design of programming languages and the success of software projects."
date = "2019-08-15"
tags = ["Guide"]
slug = "3p-principle-purpose-productivity-performance"
syndicated = "https://medium.com/@fmind/3p-principle-purpose-productivity-performance-630bed7623fc"
draft = false
+++

### The Programming Trade-Off: Purpose, Productivity, Performance

![Components of the programming trade-off](/static/img/articles/3p-principle-purpose-productivity-performance/cover.webp)

Components of the programming trade-off

As programmers, we are continuously looking for languages that are performant, productive, and general purpose. Is there any programming language that currently satisfies these properties? Can we ever create one?

In this article, I present a fundamental trade-off that affects the design of programming languages and the success of software projects.

### Definitions

**The programming trade-off dictates that a programming language cannot satisfy the following desirable properties at the same time:**

- **(General) Purpose**: a programming language can be applied to a wide range of tasks and problems (e.g., web programming, computer security, theorem proving, data analysis …).
- **Productivity**: a programming language that provides several mechanisms to deliver effective programs under time constraints (e.g., dynamic typing, introspection, meta-programming, REPL development …).
- **Performance**: a programming language that imposes a set of constraints to produce code which is both fast and efficient to execute by a computer (e.g., static typing, compilation, manual memory management, unboxed types …).

### Trade-offs

Let’s focus first on the trade-off between performance and productivity.

On the one hand, some languages like C and Assembly work closer to the hardware and are more performant than their counterparts. On the other hand, other languages such as LISP and Python provide many convenient features to boost the productivity of programmers.

We can infer the following rules to generalize these observations:

> **A programming language is performant if and only if the language provides a set of features close to the logic of a computer.**

> **A programming language is productive if and only if the language provides a set of features close to the logic of a programmer.**

> **Since the logic of a computer is different from the logic of a programmer, the task of optimizing both the performance and the productivity of a programming language is not possible.**

This dichotomy, [already described by John Ousterhout](https://en.wikipedia.org/wiki/Ousterhout%27s_dichotomy), is a well-known divergence for programming languages. However, the programming trade-off states that this limitation can be addressed if language designers choose to limit the scope of their language. It is only at this condition that language features can become more essential both for the programmer to leverage and for the computer to execute.

We can see that the programming trade-off is a direct application of the [divide-and-conquer technique](https://en.wikipedia.org/wiki/Divide_and_rule) to the creation of programming languages. For instance, SQL has one and only goal: managing database information based on relational algebra semantics. Other Domain-Specific Languages (DSL) are created to deal with narrow tasks such as web templating (Jinja), matrix manipulation (numpy), or logic programming (Prolog).

> **By reducing the scope of programming languages, programmers have the opportunity to improve both the performance and the productivity of their solutions.**

### Take-home message

If ignored, the programming trade-off can harm the success of software projects.

When I was working as a web developer, my mission was to deliver full-featured applications as fast as I can. But as the user base grew, my tasks shifted more and more toward improving the performance of the application.

[Facebook](https://code.fb.com/web/hiphop-for-php-move-fast/) and [Twitter](https://www.infoq.com/articles/twitter-java-use) faced the same problem and had to scale their websites without sacrificing their ability to develop new features.

In all these cases, most programming languages do not help as they are either too slow to execute (e.g. Python, R) or too slow to develop with (Java, C++).

**The most common solution to address this issue is often to rewrite the application with a different (and often incompatible) language.**

Other solutions can mitigate the need to rewrite existing applications:

- **Create and explore specific-purpose programming languages** (e.g., query languages, data pipelines, programming paradigms …)
- **Embrace** [**Polyglot Programming**](https://deanwampler.github.io/polyglotprogramming/) to combine the strength of several languages (e.g., TensorFlow relies both on C++ for performance and Python productivity).
- **Remember that** [**premature optimization is the root of all evil**](http://wiki.c2.com/?PrematureOptimization), it is often more important to explore the edge cases of a problem before optimizing a narrow path.
- **Remember that the requirements of a project will change over time**, the ability to adapt to new requirements remains important through the course of a project.
