+++
title = "Become the maestro of your MLOps abstractions"
description = "The MLOps ecosystem is evolving into a sophisticated symphony, composed of diverse tools, methodologies, and cultures. This diversity…"
date = "2024-01-30"
tags = ["MLOps", "Python"]
slug = "become-the-maestro-of-your-mlops-abstractions"
syndicated = "https://medium.com/@fmind/become-the-maestro-of-your-mlops-abstractions-ca6e814f13f8"
draft = false
+++

The MLOps ecosystem is evolving into a sophisticated symphony, composed of diverse tools, methodologies, and cultures. This diversity, while beneficial, also introduces a complexity reminiscent of the challenges encountered in [Big Data systems](https://en.wikipedia.org/wiki/Big_data). Data experts had to navigate through immense data characterized by its [Volume, Variety, and Velocity](https://www.techtarget.com/whatis/definition/3Vs). Such intricacies can lead to a state of [analysis paralysis](https://en.wikipedia.org/wiki/Analysis_paralysis), where decision-makers are inundated with options, hesitant to commit for fear of poor design choices.

To manage this complexity, it became essential to develop and own [**abstractions**](https://en.wikipedia.org/wiki/Abstraction) that encapsulate the underlying complexity, offering a seamless and adaptable architecture for integrating new components**.** For instance, [Apache Spark](https://spark.apache.org/) emerged as an exemplary abstraction for managing Big Data applications at scale, courtesy of its immutable and lazy programming approach. Complementary systems like [Hive Metastore](https://hive.apache.org/) further enriched the ecosystem with its capabilities. This raises a pivotal question: Can similar solutions be adopted for MLOps?

![Photo by Julio Rionaldo on Unsplash](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/cover.webp)

Photo by [Julio Rionaldo](https://unsplash.com/@juliorionaldo?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

In this article, I aim to delineate a roadmap for constructing robust MLOps platforms and projects**.** Initially, I will underscore the importance of devising and mastering your own MLOps abstractions. Following this, I will outline key design patterns essential for forging simple yet potent abstractions for your projects. Lastly, I will delve into real-world case studies, illustrating the critical role of abstractions in the success of various projects.

### Why are abstractions essential for MLOps?

[An MLOps platform encompasses various components](https://docs.zenml.io/concepts/stack_components) for training, tracking, deploying, and monitoring AI/ML models. It also integrates with data solutions like data warehouses, lakes, and catalogs. Each component has numerous proprietary and open-source solutions. Over time, these components may undergo changes, be it through upgrades or replacements with more efficient alternatives.

![THE 2023 MAD (MACHINE LEARNING, ARTIFICIAL INTELLIGENCE & DATA) LANDSCAPE](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/02.webp)

[THE 2023 MAD (MACHINE LEARNING, ARTIFICIAL INTELLIGENCE & DATA) LANDSCAPE](https://mattturck.com/landscape/mad2023.pdf)

Direct integration of each component in a project poses several risks. On one hand, it can decelerate project development as each modification or addition demands extensive refactoring. On the other hand, changes might be necessitated due to shifts in organizational infrastructure, vendor negotiations, or the need to accommodate new technology stacks.

**Abstractions** offer a solution to these challenges. By utilizing flexible abstractions, you can facilitate the addition of new components over time, avoiding direct implementation dependencies. This architectural approach is so prevalent in our industry that it’s encapsulated in a gold principle known as [**SOLID**](https://en.wikipedia.org/wiki/SOLID):

- ***S*ingle Responsibility Principle **— A class should have one, and only one, reason to change.
- __*O*pen/Closed Principle__ — Software entities should be open for extension, but closed for modification.
- __*L*iskov Substitution Principle__ — Objects in a program should be replaceable with instances of their subtypes without altering the correctness of that program.
- __*I*nterface Segregation Principle__ — No client should be forced to depend on methods it does not use.
- ***D*ependency Inversion Principle **— High-level modules should not depend on low-level modules. Both should depend on abstractions.

### Why should I own my MLOps abstractions?

Creating your own abstractions in MLOps is essential due to [the absence of a universal standard](https://mlops.community/we-need-posix-for-mlops/) like [POSIX for UNIX systems](https://en.wikipedia.org/wiki/POSIX) in our industry. Diverse model libraries such as Scikit-learn, XGBoost, PyTorch, Lightning, TensorFlow, and JAX present different interfaces for managing AI/ML models. Similarly, platforms like GCP, Azure, and Databricks offer varied toolkits for training and serving models. Relying solely on a single toolkit or platform can stifle innovation and confine you to solutions with limited control.

![Photo by Martijn Baudoin on Unsplash](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/03.webp)

Photo by [Martijn Baudoin](https://unsplash.com/@martijnbaudoin?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

By developing your own abstractions, you gain the flexibility to adopt solutions at your pace, conceal unnecessary complexities, and achieve interoperability by integrating multiple systems as needed. The investment in creating your own abstractions, if executed effectively, is manageable. Consider the universality of USB-C for computer I/O or Docker for application portability as analogous examples.

However, it’s important to be cautious of ‘[leaky abstractions](https://en.wikipedia.org/wiki/Leaky_abstraction)’, which can adversely impact your project. Crafting effective abstractions requires time and expertise. When uncertain, it’s advisable to start with minimal abstractions and expand them gradually, tailoring them to your project’s core components. Avoid over-anticipating your abstraction needs. Instead, address issues as they emerge and devise solutions that are most appropriate for the immediate challenges at hand.

### Design Patterns 101

[**Design patterns**](https://en.wikipedia.org/wiki/Design_Patterns) serve as invaluable tools for creating abstractions, offering standardized solutions to recurrent problems. These patterns simplify the design process by providing proven techniques adaptable to various contexts, including MLOps. Let’s delve into the three primary types of design patterns and their application in MLOps environments. I also encourage you to check [this article from Laszlo SRAGNER](https://laszlo.substack.com/p/you-only-need-2-design-patterns-to) and [his slides from PyData London 2022](https://laszlo.substack.com/p/slides-for-my-talk-at-pydata-london) if you want to learn more about design patterns for MLOps.

#### Behavioral pattern: Strategy (Abstract)

The [**Strategy pattern**](https://en.wikipedia.org/wiki/Strategy_pattern) is instrumental in MLOps for its ability to **abstract** the “what” from the “how” in algorithmic operations. In MLOps, this translates to separating the goal (e.g., model training) from the method (e.g., using TensorFlow, XGBoost, or PyTorch). By employing the Strategy pattern, different algorithms or frameworks can be interchanged without altering the code structure, adhering to the Open/Closed Principle. This flexibility is crucial for MLOps, allowing dynamic adaptations like switching models or data sources based on runtime conditions.

![Strategy pattern : define a Model interface to switch between AI/ML frameworks at runtime](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/04.webp)

**Strategy pattern**: define a Model interface to switch between AI/ML frameworks at runtime

#### Creational pattern: Factory (Adapt)

Following the establishment of common interfaces, the [**Factory pattern**](https://en.wikipedia.org/wiki/Factory_method_pattern) becomes essential for dynamically **adapting** program behavior at runtime. This pattern facilitates object creation, enabling control through external configurations. In MLOps, this means allowing users to modify the scope and settings of AI/ML pipelines without changing the codebase. Python’s dynamic nature, coupled with tools like [Pydantic](https://docs.pydantic.dev/latest/) and its [Discriminated Union](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions-with-str-discriminators) feature, simplifies implementing this pattern, enhancing user input validation and program object instantiation.

![Factory pattern : instantiate Model objects from model name using external configurations](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/05.webp)

**Factory pattern**: instantiate Model objects from model name using external configurations

#### Structural pattern: Adapter (Overcome)

Given the lack of a unified standard in MLOps, the [**Adapter pattern**](https://en.wikipedia.org/wiki/Adapter_pattern) plays a critical role. It acts as a bridge between disparate systems, **overcoming** incompatible interfaces. This pattern is particularly valuable in MLOps for integrating various external components, such as training and inference systems, across different platforms (like Databricks and Kubernetes for instance). By employing an Adapter, calls from one system can be translated and made compatible with another, ensuring seamless integration and generalization of external components.

![Adapter pattern : translate torch and sklearn interfaces to your own project abstractions](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/06.webp)

**Adapter pattern**: translate torch and sklearn interfaces to your own project abstractions

### Examples

To illustrate the design patterns highlighted in the previous section, let’s take 3 examples to motivate their uses and their benefits for MLOps projects.

#### Case 1: ZenML (Full-Stack)

[**ZenML**](https://www.zenml.io/) emerges as [a comprehensive solution for integrating MLOps components](https://www.zenml.io/blog/zenml-why-we-built-it). Rather than developing bespoke abstractions, ZenML’s built-in offerings facilitate a swift initiation of your projects, allowing for custom abstractions as needed. This represents a significant undertaking by the ZenML team, as it involves [integrating and adapting various libraries to meet standard specifications](https://www.zenml.io/integrations).

ZenML proves especially valuable in ecosystems that utilize diverse software stacks (e.g., Databricks, SageMaker, Kubernetes, etc.), or when there’s a need to rapidly switch or incorporate other solutions. It exemplifies how design patterns can simplify user experiences and harmonize development environments.

![Become the maestro of your MLOps abstractions](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/07.webp)

#### Case 2: Evidently (Monitoring)

My recent adoption of [**Evidently**](https://www.evidentlyai.com/) to power a monitoring stack was prompted by a review of vendor solutions that [lacked essential features](https://fmind.medium.com/is-ai-ml-monitoring-just-data-engineering-10a2525a9c73). Evidently offers notable capabilities, [such as generating metrics and dashboards](https://docs.evidentlyai.com/examples/introduction) that can be ingested in our MLOps platform:

```python
report = Report(metrics=[
    DataDriftPreset(),
])

report.run(reference_data=reference, current_data=current)
report
```

![Data Drift report overview](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/08.webp)

[Data Drift report overview](https://docs.evidentlyai.com/examples/introduction)

However, Evidently [does not support tabular exports yet](https://docs.evidentlyai.com/docs/library/output_formats). While contributing to Evidently’s codebase is appealing, employing design patterns strategically is imperative for the short-term adoption of the solution and safeguarding our codebase [against external uncertainties](https://web.archive.org/web/20240203173056/https://www.seldon.io/resources/licensing-faqs).

#### Case 3: MLOps Python Package (Development)

I recently introduced a GitHub repository showcasing tips for crafting an [**MLOps Python Package**](https://www.fmind.dev/articles/a-great-mlops-project-should-start-with-a-good-python-package/). This [repository](https://github.com/fmind/mlops-python-package) exemplifies some patterns discussed in this article.

For example, the package offers [an interface for unifying AI/ML models](https://github.com/fmind/mlops-python-package/blob/618b83a0f1d8f218d131a8f415e95a44929654af/src/wines/models.py) from various frameworks (e.g., sklearn, pytorch), demonstrating the [strategy pattern](https://en.wikipedia.org/wiki/Strategy_pattern).

```python
import abc
import typing as T
import pydantic as pdt
from sklearn import ensemble, pipeline

ParamKey = str
ParamValue = T.Any
Params = T.Dict[ParamKey, ParamValue]

class Model(abc.ABC, pdt.BaseModel):
    """Base class for a model."""

    KIND: str

    def get_params(self, deep: bool = True) -> Params:
        """Get the model params."""
        params: Params = {}
        for key, value in self.dict().items():
            if not key.startswith("_") and not key.isupper():
                params[key] = value
        return params

    def set_params(self, **params: ParamValue) -> "Model":
        """Set the model params in place."""
        for key, value in params.items():
            setattr(self, key, value)
        return self

    @abc.abstractmethod
    def fit(self, inputs: schemas.Inputs, target: schemas.Target) -> "Model":
        """Fit the model on the given inputs and target."""

    @abc.abstractmethod
    def predict(self, inputs: schemas.Inputs) -> schemas.Output:
        """Generate an output with the model for the given inputs."""
```

It also features a [high-level job API](https://github.com/fmind/mlops-python-package/blob/618b83a0f1d8f218d131a8f415e95a44929654af/src/wines/jobs.py), enabling users to alter the task type via configuration files. The package readily supports Tuning, Training, and Inference jobs, showcasing the [factory pattern](https://en.wikipedia.org/wiki/Factory_method_pattern)’s role in initiating programs based on external settings.

```python
import abc
import typing as T
import pydantic as pdt

Locals = T.Dict[str, T.Any]

class Job(abc.ABC, pdt.BaseModel):
    """Base class for a job."""

    KIND: str

    @abc.abstractmethod
    def run(self) -> Locals:
        """Run the job in context."""

class TrainingJob(Job):
    """Train and register a single AI/ML model"""

    KIND: T.Literal["TrainingJob"] = "TrainingJob"

    inputs: datasets.DatasetKind
    target: datasets.DatasetKind
    model: models.ModelKind = models.BaselineSklearnModel()
    metric: metrics.MetricKind = metrics.SklearnMetric()

    def run(self) -> Locals:
        """Run the training job in context."""
        # lots of code here ...
        return locals()
```

Lastly, the package incorporates an [adapter pattern](https://en.wikipedia.org/wiki/Adapter_pattern) for [configuration file loading](https://github.com/fmind/mlops-python-package/blob/618b83a0f1d8f218d131a8f415e95a44929654af/src/wines/configs.py). Although [OmegaConf](https://omegaconf.readthedocs.io/) can parse and merge YAML files, it lacks native support for cloud storage like S3 or GCP. Integrating with the [cloudpathlib](https://cloudpathlib.drivendata.org/stable/) package allows for configuration file access from any location, seamlessly hiding internal complexities.

```python
import typing as T
from cloudpathlib import AnyPath
from omegaconf import DictConfig, ListConfig, OmegaConf

Config = T.Union[ListConfig, DictConfig]

def load_config(path: str) -> Config:
    """Load a configuration file."""
    any_path = AnyPath(path)
    text = any_path.read_text()
    config = OmegaConf.create(text)
    return config
```

### Conclusions: Abstract, Adapt, Overcome

This article exemplifies how design patterns can be effectively utilized to evolve MLOps codebases and facilitate the integration of external components. This approach aligns with [David J. Wheeler’s foundational theorem of software development](https://en.wikipedia.org/wiki/Fundamental_theorem_of_software_engineering), which posits, _‘We can solve any problem by introducing an extra level of indirection’._ Crafting robust abstractions requires time and [thoughtful consideration](https://www.youtube.com/watch?v=f84n5oFoZBc); often, it’s wiser to start without them and then implement them to encapsulate emerging patterns.

![Become the maestro of your MLOps abstractions](/static/img/articles/become-the-maestro-of-your-mlops-abstractions/09.webp)

While abstractions offer significant benefits, they cannot fully address the ‘curse of components’ inherent in the [MLOps landscape](https://mattturck.com/landscape/mad2023.pdf). The sheer complexity of integrating every conceivable solution in the market with others presents a daunting, perhaps intractable, challenge. This complexity could potentially stifle innovation and hinder long-term integration efforts. The concept of a **‘** [**Language of the System**](https://www.youtube.com/watch?v=ROor6_NGIWU) **’**, as articulated by Rich Hickey in his insightful talk, could be a game-changer for MLOps in this regard. Until such a paradigm emerges, the best practice is to maintain strong abstractions and strive for simplicity in your codebase.
