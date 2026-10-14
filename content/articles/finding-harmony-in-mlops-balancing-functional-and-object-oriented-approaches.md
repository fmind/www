+++
title = "Finding Harmony in MLOps: Balancing Functional and Object-Oriented Approaches ☯"
description = "Programmers have always been passionate about their preferences, whether they discuss spaces vs. tabs, Vim vs. Emacs, or light mode vs. dark mode."
date = "2023-07-31"
tags = ["MLOps", "Python"]
slug = "finding-harmony-in-mlops-balancing-functional-and-object-oriented-approaches"
syndicated = "https://medium.com/@fmind/finding-harmony-in-mlops-balancing-functional-and-object-oriented-approaches-503591be6d9b"
draft = false
+++

Programmers have always been passionate about their preferences, whether they discuss [spaces vs. tabs](https://alexkondov.com/indentation-warfare-tabs-vs-spaces/#:~:text=The%20Tab%20Character&text=It%20is%20interpreted%20by%20the,tab%20character%20represents%20multiple%20whitespaces.), [Vim vs. Emacs](https://en.wikipedia.org/wiki/Editor_war), or [light mode vs. dark mode](https://www.nngroup.com/articles/dark-mode/). These debates have withstood the test of time, indicating that there is a place for each solution, and no definitive argument can declare one superior over the other.

However, when it comes to programming paradigms, the arguments tend to be more fervent. [Object-oriented languages](https://en.wikipedia.org/wiki/Object-oriented_programming) have [long dominated the programming landscape](https://www.tiobe.com/tiobe-index/), championing code reusability across various projects. In contrast, [functional programming](https://en.wikipedia.org/wiki/Functional_programming) has emerged as an alternative style in recent years, [promising code that is easier to reason with](https://www.youtube.com/watch?v=SxdOUGdseq4). When delving into machine learning projects, the question arises: **which paradigm is best suited for building an MLOps application?**

![Photo by Alex Padurariu on Unsplash](/static/img/articles/finding-harmony-in-mlops-balancing-functional-and-object-oriented-approaches/cover.webp)

Photo by [Alex Padurariu](https://unsplash.com/@alexpadurariu?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com/?utm_source=medium&utm_medium=referral)

This article aims to shed light on the benefits of both programming styles and help you determine the most suitable one for your MLOps project. We will start by introducing the two main programming styles in our industry. Subsequently, we will explore the specific requirements of MLOps projects to guide our decision-making process. Finally, I will offer my opinion on the best overall style and present a compelling trade-off known as the “hybrid style.”

### A brief intro to programming paradigms

Throughout my career, I’ve had the chance of working with various programming languages, starting with object-oriented ones like C++, Java, PHP, Python, Ruby, and Groovy. Each language offers its own set of advantages and disadvantages, depending on the depth of its features:

### Pros:

1. [**Real-World Modeling**](https://www.baeldung.com/cs/oop-modeling-real-world): The object-oriented paradigm closely mirrors real-world entities, making it intuitive for developers to model and design applications based on the problem domain.
2. [**Modularity and Reusability**](https://www.tutorialspoint.com/understanding-code-reuse-and-modularity-in-python-3#:~:text=Modularity%20refers%20to%20the%20act,thrives%20to%20minimize%20the%20duplication.): Object-oriented programming’s encapsulation allows for modular code design, promoting reusability and maintainability. This helps manage large codebases and fosters collaboration among team members.
3. [**Rich Ecosystem**](https://bookauthority.org/books/best-object-oriented-design-books): Object-oriented programming languages like Java and C# have extensive frameworks and design patterns, providing developers with powerful tools for building complex applications efficiently.

### Cons:

1. [**Shared Mutable State**](https://softwareengineering.stackexchange.com/questions/235558/what-is-state-mutable-state-and-immutable-state): Object-oriented programming often relies on a shared mutable state, leading to potential bugs and issues related to mutable objects being accessed from multiple locations.
2. [**Brittle Inheritance Hierarchies**](https://softwareengineering.stackexchange.com/questions/134097/why-should-i-prefer-composition-over-inheritance): Overuse of inheritance can lead to fragile class hierarchies, making it difficult to modify or extend functionality without introducing unintended side effects.
3. [**Complexity and Overhead**](https://en.wikipedia.org/wiki/Anti-pattern): Object-oriented codebases can become complex, especially in large projects, leading to increased development and debugging time.

Below is a diagram illustrating an MLOps application implemented with an object-oriented style. The programmer must carefully handle the object attributes, and provide getter/setter methods to control their access. While the program representation is intuitive, it is also verbose and sometimes rigid with its adherence to object-oriented principles.

![Simplified MLOps application implemented with the Object-Oriented Style](/static/img/articles/finding-harmony-in-mlops-balancing-functional-and-object-oriented-approaches/02.webp)

Simplified MLOps application implemented with the Object-Oriented Style

As my career progressed, I ventured into functional-oriented languages such as Clojure, Haskell, and Elixir. These languages piqued my interest with their unique approach to state management and other concepts that [seemed tailored for data applications](https://towardsdatascience.com/the-ultimate-guide-to-functional-programming-for-big-data-1e57b0d225a3).

### Pros:

1. [**Enhanced reasoning capabilities**](https://en.wikipedia.org/wiki/Pure_function): Functional programming’s focus on pure functions ensures that executions solely depend on inputs, making testing and debugging significantly more straightforward.
2. [**Predictable Concurrency**](https://kyleshevlin.com/just-enough-fp-immutability): Immutability and statelessness inherently reduce the chances of race conditions and concurrent data access issues, making it more suitable for parallel and concurrent programming.
3. [**Simplicity in design**](https://www.youtube.com/watch?v=SxdOUGdseq4): Functional programming requires fewer complex design patterns, relying instead on other forms of [polymorphism](https://en.wikipedia.org/wiki/Polymorphism_%28computer_science%29) (e.g., ad-hoc or parametric), [high-order functions](https://en.wikipedia.org/wiki/Higher-order_function), and even [monads](https://en.wikipedia.org/wiki/Monad_%28functional_programming%29) to extend and fortify programs.

### Cons:

1. [**Learning Curve**](https://www.infoworld.com/article/2843393/functional-programming-tradeoffs-efficiency-learning-curve.html): Functional programming can be challenging for developers who are more accustomed to imperative and object-oriented paradigms. The shift in mindset and understanding of concepts like higher-order functions and recursion may take time.
2. [**Performance Overhead**](https://stackoverflow.com/questions/8659345/why-is-this-simple-haskell-algorithm-so-slow): Some functional programming constructs, such as creating many intermediate data structures during computation, may introduce performance overhead compared to optimized imperative implementations.

The diagram below exemplifies an MLOps application adhering to a functional programming style. The program layout is more straightforward due to a clear separation between data structures and operations. However, this style requires functional programming constructs such as [ad-hoc polymorphism](https://www.haskell.org/tutorial/classes.html) to support the addition of both new types and functions in a robust manner.

![Simplified MLOps application implemented with the Functional Programming Style](/static/img/articles/finding-harmony-in-mlops-balancing-functional-and-object-oriented-approaches/03.webp)

Simplified MLOps application implemented with the Functional Programming Style

Mastering both paradigms proves to be a valuable investment, equipping developers with a diverse toolkit to design optimal solutions. Let’s now explore the specific requirements unique to MLOps projects, aiding us in selecting the best-suited programming style for this type of application.

### Requirements for MLOps projects

MLOps applications present a unique blend of simplicity and complexity. On one hand, they share common concepts like datasets, models, and jobs, which can be reused across projects with slight variations. However, dealing with challenges like randomness, large data structures, and complex internal objects, such as neural networks, adds complexity to these projects. To avoid potential struggles and costly refactoring, starting MLOps applications with a well-designed foundation is crucial.

Below, we list key requirements ranked by importance for an MLOps application (in my opinion):

1. [**Reproducibility**](https://en.wikipedia.org/wiki/Reproducibility): Ensure that your MLOps application produces consistent and reproducible results.
2. [**Modularity**](https://en.wikipedia.org/wiki/Modularity): Embrace modularity by breaking down your MLOps application into smaller, reusable components.
3. [**Configurability**](https://en.wikipedia.org/wiki/Software_configuration_management): Allowing program behavior changes through external configurations rather than direct code modifications.
4. [**Extensibility**](https://en.wikipedia.org/wiki/Extensibility): Facilitating the addition of new models and data sources.
5. [**Keep It Simple (KISS)**](https://en.wikipedia.org/wiki/KISS_principle): Keep the application simple, as not all MLOps contributors have advanced programming backgrounds.

With these requirements in mind, let’s delve into the discussion of which programming style might be best suited for developing MLOps applications.

### So, which style is best?

As we explored the pros and cons of both object-oriented and functional programming in the previous section, we see that **there is no single criterion that strongly favors one over the other for MLOps applications**. Both styles can meet the identified requirements, which is fortunate, considering most programming languages are [Turing complete and offer equivalent expressivity](https://en.wikipedia.org/wiki/Turing_completeness).

However, I do have a compelling argument. **While all programming styles can be applied to develop MLOps applications, not all programming languages can effectively support both paradigms**. For instance, [Python, one of the most popular languages for data science projects](https://www.datacamp.com/blog/top-programming-languages-for-data-scientists-in-2022), is best suited for object-oriented programming when building large applications. Though it can handle functions and even high-order functions, these features represent the bare minimum to support the functional paradigm. Python lacks support for key elements of functional programming, such as 1) [ad-hoc or parametric polymorphism](https://en.wikipedia.org/wiki/Polymorphism_%28computer_science%29), 2) [tail-call optimization](https://wiki.c2.com/?TailCallOptimization=), and 3) efficient immutable data structures (e.g., [persistent data structures](https://en.wikipedia.org/wiki/Persistent_data_structure)). In contrast, it excels at using [subtyping polymorphism](https://en.wikipedia.org/wiki/Subtyping) and [mutability](https://en.wikipedia.org/wiki/Immutable_object) for various Python operations.

As a result, **I tend to favor the object-oriented paradigm when building MLOps applications with Python**, **even if I prefer the functional paradigm for other application types**. Building an MLOps project is not trivial, as it requires advanced and idiomatic language features to fulfill specific requirements. Nevertheless, there is a trick that can be applied to incorporate elements of both paradigms, striking a balance that leverages the strengths of each approach.

### The Hybrid Style

The hybrid style aims to combine the best aspects of functional programming with the object-oriented paradigm, creating a favorable trade-off for programming languages like Python that support both styles. By embracing this approach, your code can become more idiomatic, extensible, and easier to reason with.

To implement this style effectively, consider adhering to the following principles:

1. [**Immutable attributes**](https://en.wikipedia.org/wiki/Immutable_object): Objects should not update their attributes after initialization, treating them as read-only to avoid modifying the object state directly.
2. **Output-oriented methods**: Each method should return its output rather than updating attributes, enabling other objects to handle modifications to the program state.
3. [**Idempotent method calls**](https://en.wikipedia.org/wiki/Idempotence): methods should consistently return the same output for the given inputs, akin to functional programming principles.
4. [**Centralized imperative statements**](https://www.haskell.org/tutorial/io.html): High-level classes, like a Job class, should handle imperative statements, a concept reminiscent of [the IO monad in Haskell](https://en.wikibooks.org/wiki/Haskell/Understanding_monads/IO). This ensures clear demarcation of actions that interact with the real world, such as logging or database updates.
5. [**Leverage object-oriented other benefits**](https://en.wikipedia.org/wiki/Object-oriented_programming): Embrace the advantages of object-oriented programming, such as subtyping polymorphism and intuitive representations when needed.

This final diagram presents an MLOps application following the hybrid style’s guidelines. On one hand, we fall back to [subtyping polymorphism](https://en.wikipedia.org/wiki/Subtyping) and class representations to support the program's extensibility. On the other hand, we reduce the overhead of managing the program state by using and sharing read-only attributes while separating the classes that might have a side effect (i.e., jobs) from the rest of the application.

![Simplified MLOps application implemented with the Hybrid Style](/static/img/articles/finding-harmony-in-mlops-balancing-functional-and-object-oriented-approaches/04.webp)

Simplified MLOps application implemented with the Hybrid Style

**Remember that these are guiding principles rather than strict rules**. By applying them thoughtfully, you can design a robust application. The [MLOps Python Package](https://fmind.medium.com/a-great-mlops-project-should-start-with-a-good-python-package-7662bdf79563) was developed using these principles and can demonstrate how the hybrid style can be applied effectively to MLOps applications.

### Conclusions

This article explored the strengths and weaknesses of two popular programming paradigms: [Functional](https://en.wikipedia.org/wiki/Functional_programming) and [Object-oriented](https://en.wikipedia.org/wiki/Object-oriented_programming). Both styles can be successfully applied to MLOps projects, considering their unique requirements. **The primary selection criterion should align with your chosen programming language’s characteristics, allowing you to implement the most idiomatic solutions**. For instance, opt for a functional style with Haskell or Clojure and an object-oriented style with Java or Python.

Alternatively, you can leverage the hybrid style to blend the benefits of functional and object-oriented approaches in a predominantly object-oriented language. This choice respects the language’s capabilities while catering to data applications where idempotence and parallelism play crucial roles in taking your application to the next level.

On a personal note, I find the object-oriented style of Python somewhat lacking in elegance. However, I hold Python in high regard for its adaptability to new concepts over time, such as [gradual typing](https://docs.python.org/3/library/typing.html) or [asynchronous programming](https://docs.python.org/3/library/asyncio.html). To improve Python’s object-oriented style, I recommend using a toolkit like [Pydantic](https://docs.pydantic.dev/latest/), a remarkable library that I’ve extensively employed in designing the [MLOps Python Package](https://fmind.medium.com/a-great-mlops-project-should-start-with-a-good-python-package-7662bdf79563). It overcomes the aforementioned limitation and significantly enhances the development process.

![Photo by Nathan Dumlao on Unsplash](/static/img/articles/finding-harmony-in-mlops-balancing-functional-and-object-oriented-approaches/05.webp)

Photo by [Nathan Dumlao](https://unsplash.com/@nate_dumlao?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com/?utm_source=medium&utm_medium=referral)
