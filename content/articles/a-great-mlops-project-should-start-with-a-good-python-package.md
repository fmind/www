+++
title = "A great MLOps project should start with a good Python Package 🐍"
description = "MLOps practitioners (rightfully) point out that running notebooks in production is a bad software practice, but what are the alternatives…"
date = "2023-06-24"
tags = ["MLOps", "Python", "Project"]
slug = "a-great-mlops-project-should-start-with-a-good-python-package"
syndicated = "https://medium.com/@fmind/a-great-mlops-project-should-start-with-a-good-python-package-7662bdf79563"
draft = false
+++

MLOps practitioners (rightfully) point out [that running notebooks in production is a bad software practice](https://www.youtube.com/watch?v=7jiPeIFXb6U), but what are the alternatives? A simple script is not enough to capture the complexity of AI/ML projects, and rewriting a whole project in another programming language is both costly and time-consuming.

To solve this problem, **the most efficient approach is to create a** [**Python package**](https://packaging.python.org/en/latest/overview/) that compiles the project sources and assets in a [code archive](https://pythonwheels.com/). However, building such a package can be a complex endeavor for newcomers. The Python ecosystem is [vibrant](https://github.com/topics/python), but also [fragmented](https://xkcd.com/1987/). Moreover, [machine learning projects are more complex to develop than most other software applications](https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html).

![Python Environment: https://xkcd.com/1987/](/static/img/articles/a-great-mlops-project-should-start-with-a-good-python-package/cover.webp)

Python Environment: [https://xkcd.com/1987/](https://xkcd.com/1987/)

**In this article, I present the implementation of a** [**Python package on GitHub**](https://github.com/fmind/mlops-python-package) **designed to support MLOps initiatives**. The goal of this package is to make the coding workflow of data scientists and ML engineers as flexible, robust, and productive as possible. First, I start by motivating the use of Python packages. Then, I provide some tools and tips you can include in your MLOps project. Finally, I explain the follow-up steps required to take this package to the next level and make it work in your environment.

**Link to the repository -** [**https://github.com/fmind/mlops-python-package**](https://github.com/fmind/mlops-python-package)

### Motivations

[Building Python packages is a common practice in our industry](https://github.com/topics/python). A Python package allows developers to collaborate with others, version the source code, and share code archives on a package index such as [Pypi.org](https://pypi.org/). Another benefit is that Python package can be used both as a library (i.e., imported from another code base) and an application (i.e., be executed from the command line). Python developers are also used to leverage packages developed by others, such as [Flask](https://flask.palletsprojects.com/en/latest/), [Pandas](https://pandas.pydata.org/), or [TensorFlow](https://www.tensorflow.org/) just to name a few.

But despite all these benefits, Python packages are complex to build and structure properly. On one hand, [**there are a lot of tools to combine**](https://xkcd.com/1987/) and it can be difficult for developers to choose the best components without hands-on experience. On the other hand, [**machine learning is one of the most complex types of projects**](https://papers.nips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html), as data dimensions, randomness, and entangled workflows make everything more difficult.

In my career, I spend hours researching the best set of tools and tricks to make this experience as optimal as possible for data scientists, ML engineers, and myself. I hope this initiative will help you in your MLOps journey and this will let you build great AI/ML solutions for your use cases.

![The General Problem: https://xkcd.com/974/](/static/img/articles/a-great-mlops-project-should-start-with-a-good-python-package/02.webp)

The General Problem: [https://xkcd.com/974/](https://xkcd.com/974/)

### Tools & Tips

The [GitHub repository](https://github.com/fmind/mlops-python-package) provides both the implementation and the design decisions for developing with the MLOps Python package. You can get all the main information in the [README.md](https://github.com/fmind/mlops-python-package/blob/main/README.md) file. Before jumping to the tools and tips, I’d like to highlight the “methodology” for selecting the elements in this package:

- [**Keep It Simple Stupid (KISS)**](https://en.wikipedia.org/wiki/KISS_principle): data scientists and ML engineers are dealing with complex tasks (e.g., maths, software development, business requirements, …). The package should get out of their way as much as possible and be simple to read and follow.
- **Leverage good software practices**: our nascent MLOps industry can benefit from years of software experience. We can leverage [design patterns](https://en.wikipedia.org/wiki/Software_design_pattern) and the [Python ecosystem](https://github.com/ml-tooling/best-of-python-dev) to make our development environment as powerful as possible.
- **The constant trade-off of simplicity vs power**: creating an empty shell or a technical show-off is easy. The real struggle in creating such a package is to bring the best practice possible while making it accessible to the majority of end users.

The [MLOps Python Package](https://github.com/fmind/mlops-python-package#tools) includes more than 30 tools. My favorite ones are:

- [**Mypy**](https://github.com/fmind/mlops-python-package#typing-mypy): check that your [code types](https://docs.python.org/3/library/typing.html) are valid during development.
- [**OmegaConf**](https://github.com/fmind/mlops-python-package#parser-omegaconf): parse and merge YAML files to load configurations.
- [**Pydantic**](https://github.com/fmind/mlops-python-package#validator-pydantic): better definition and validation of Python classes (check out [**Tagged Union**](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions), this is a great way to [initialize your program](https://en.wikipedia.org/wiki/Creational_pattern)!).
- [**Invoke**](https://github.com/fmind/mlops-python-package#tasks-pyinvoke): define development tasks in a saner syntax than Makefile.
- [**Poetry**](https://github.com/fmind/mlops-python-package#manager-poetry): manage your Python package (metadata, dependencies, …).

The [MLOps Python Package](https://github.com/fmind/mlops-python-package) also includes more than 20 tips and tricks. The most important ones are:

- [**SOLID Principles**](https://github.com/fmind/mlops-python-package#solid-principles): define software interface to make your code more modular and reusable.
- [**Soft Coding**](https://github.com/fmind/mlops-python-package#soft-coding): change your program behavior through config files instead of code changes.
- [**Data Catalog**](https://github.com/fmind/mlops-python-package#data-catalog): [separate the data you want to access from how you access it](https://www.youtube.com/watch?v=D6nYfttnVco)
- [**Text Fixture**](https://github.com/fmind/mlops-python-package#test-fixtures): create contextual objects to support [Test-Driven Development](https://en.wikipedia.org/wiki/Test-driven_development) (TDD) with [Pytest](https://docs.pytest.org/en/latest/).
- [**DataFrame Typing**](https://github.com/fmind/mlops-python-package#dataframe-typing): define dataframe schemas to communicate their fields and validate them with [Pandera](https://pandera.readthedocs.io/).

PS: I know several people who complain that [Python is a bad programming language](https://medium.com/nerd-for-tech/python-is-a-bad-programming-language-2ab73b0bda5). On the contrary, I think Python can be a great programming language with a bit of discipline and the right tooling!

![Python: https://xkcd.com/353/](/static/img/articles/a-great-mlops-project-should-start-with-a-good-python-package/03.webp)

Python: [https://xkcd.com/353/](https://xkcd.com/353/)

### Integrations

**Having an MLOps Python Package is** [**just a small part of your MLOps journey**](https://medium.com/marvelous-mlops/the-minimum-set-of-must-haves-for-mlops-5dbbcf29401c). While most MLOps project starts with a Python package, this artifact should be integrated with the rest of your infrastructure: Compute Engine (e.g., [Kubernetes](https://kubernetes.io/), [Databricks](https://www.databricks.com/)), Experiment Tracking (e.g., [MLflow](https://mlflow.org/), [Neptune](https://support.neptune.ai/en/articles/13925165-service-shutdown-overview)), and Task Orchestration (e.g., [Airflow](https://airflow.apache.org/), [Kubeflow](http://kubeflow.org)).

After all my research, I haven't found a one-size-fits-all infrastructure that can address everybody's use cases. On one hand, [cloud providers](https://en.wikipedia.org/wiki/Cloud_computing) provide [end-to-end solutions which are specific to their platform](https://aws.amazon.com/sagemaker/). On the other hand, [Kubernetes-based solutions have a huge learning curve](http://kubeflow.org) and are too heavyweight for data scientists. Another big issue is the lack of common protocols to easily integrate all these MLOps systems, as explained in my other article: [We need POSIX for MLOps](https://medium.com/@fmind/we-need-posix-for-mlops-e7bea8d8ec29), and more generally in this talk from Rich Hickey: [The Language of the System](https://www.youtube.com/watch?v=ROor6_NGIWU).

Thus, I created this package as a common denominator for MLOps initiatives devoided of any infrastructure dependencies. It is your task, dear reader, to extend its capabilities based on your requirements and environments to suit your end-user needs.

![Standards: https://xkcd.com/927/](/static/img/articles/a-great-mlops-project-should-start-with-a-good-python-package/04.webp)

Standards: [https://xkcd.com/927/](https://xkcd.com/927/)

### Conclusions

Using Python packages for MLOps is a good practice, but creating the best package requires a lot of [hammock-driven development](https://www.youtube.com/watch?v=f84n5oFoZBc). I hope you will find value in [this package](https://github.com/fmind/mlops-python-package) and have the best success with your MLOps project.

To reflect on this task, I like to compare programming to martial arts. The goal is not to beat your opponent with brute force tactics but to inflict the most deadly strikes in the swiftest manner. It is a balance of power, moderation, and respect for your opponent. Similarly, I think creating good software is a form of art, and a never-ending quest to surpass yourself.

As I final note, I always love to discuss development practices with my peers. Feel free to drop me a message on the [MLOps Community Slack](https://go.mlops.community/slack), [create an issue on GitHub](https://github.com/fmind/mlops-python-package/issues), or [contribute directly to the repository](https://github.com/fmind/mlops-python-package/pulls). [This is the power of open source after all](https://www.youtube.com/watch?v=9sJUDx7iEJw) :)

![A great MLOps project should start with a good Python Package 🐍](/static/img/articles/a-great-mlops-project-should-start-with-a-good-python-package/05.webp)
