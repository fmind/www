+++
title = "Make your MLOps code base SOLID with Pydantic and Python’s ABC"
description = "MLOps projects are straightforward to initiate, but challenging to perfect. While AI/ML projects often start with a notebook for…"
date = "2024-03-13"
tags = ["MLOps", "Python"]
slug = "make-your-mlops-code-base-solid-with-pydantic-and-pythons-abc"
syndicated = "https://medium.com/@fmind/make-your-mlops-code-base-solid-with-pydantic-and-pythons-abc-aeedfe9c3e65"
draft = false
+++

MLOps projects are straightforward to initiate, but challenging to perfect. While AI/ML projects often start with a notebook for prototyping, deploying them directly in production is often considered [poor practice by the MLOps community](https://www.youtube.com/watch?v=7jiPeIFXb6U). Transitioning to a dedicated Python code base is essential for industrializing the project, yet this move presents several challenges: 1) How can we maintain a code base that is robust yet flexible for agile development? 2) Is it feasible to implement proven design patterns while keeping the code base accessible to all developers? 3) How can we leverage Python’s dynamic nature while adopting strong typing practices akin to static languages?

Throughout my career, I have thoroughly explored various strategies to make my code base both simple and powerful. In 2009, I had the opportunity to collaborate with seasoned developers and enthusiasts of design patterns in object-oriented languages such as [C++](https://isocpp.org/) and [Java](https://www.java.com/en/). By 2015, I had devoted hundreds of hours to mastering functional programming paradigms with languages like [Clojure](https://clojure.org/) (LISP) and [Haskell](https://www.haskell.org/). This journey led me to discover both modern and time-tested practices, which I have applied to my AI/ML projects. I am eager to share these practices and reveal the most effective solutions I’ve encountered.

![The Three Little Pig illustrates the needs for building robust structures](/static/img/articles/make-your-mlops-code-base-solid-with-pydantic-and-pythons-abc/cover.webp)

The Three Little Pig illustrates the needs for building robust structures

**In this article, I propose a method to develop high-quality MLOps projects using Python's ABC and Pydantic**. I begin by emphasizing the importance of implementing SOLID software practices in AI/ML codebases. Next, I offer some background on design patterns and the SOLID principles. Then, I recount my experiences with various code architectures and their limitations. Finally, I explain how Python's ABC and Pydantic can enhance the quality of your Python code and facilitate the adoption of sound coding practices.

### Motivations

Let’s review the motivations for using advanced patterns in MLOps projects.

#### Freedom to Choose

AI/ML code bases are tasked with performing several critical operations:

- Reading data from various sources
- Processing data to generate diverse sets of features
- Training models using available machine-learning libraries
- Generating and evaluating predictions or content across numerous scenarios
- Adapting the code base to fit the project infrastructure, such as model registries

While supporting a single option at each of these steps is relatively straightforward, AI/ML solutions should remain flexible and adaptable. [The AI/ML field is dynamic, with better algorithms and models continuously being developed](https://paperswithcode.com/). [Data competitions highlight the importance of creativity and experimentation in achieving peak performance](https://mlcontests.com/state-of-competitive-machine-learning-2023/). Therefore, an AI/ML project must be designed with this flexibility in mind, offering the capacity to integrate new solutions over time within the same code base.

#### Robustness of the code

The dynamic nature of Python serves as both an advantage and a drawback. On one side, it offers developers the flexibility to mold the code base into any desired form, enabling the creation of innovative abstractions. However, this same flexibility can lead to disorganized code structures, often referred to humorously as [code lasagna](https://wiki.c2.com/?LasagnaCode), [code spaghetti](https://en.wikipedia.org/wiki/Spaghetti_code), and other varieties of ‘code pasta.’

Echoing the well-known adage from Spider-Man, “With great power comes great responsibility,” Python developers, more than those in other static languages, need to exercise discipline to ensure their code remains robust. This can be achieved through practices such as gradual typing, thorough validation of inputs and outputs, and the use of interfaces that clearly define the expectations for each software component.

#### Efficiency of developers

Developer time is a valuable asset, one that shouldn’t be squandered on constant refactoring or the elimination of technical debt. For example, web frameworks like Django or Flask offer a suite of abstractions that enable developers to quickly start building websites using industry-proven patterns. These frameworks afford the flexibility to switch between database systems, integrate internal objects with database tables through [Object-Relational Mapping](https://en.wikipedia.org/wiki/Object%E2%80%93relational_mapping) (ORM), or incorporate [middleware](https://en.wikipedia.org/wiki/Middleware) and callbacks to seamlessly integrate new systems.

In a similar vein, an MLOps code base should offer the same level of flexibility and efficiency. By adopting the right design patterns, developers are empowered to investigate more solutions, achieve greater productivity, and deliver enhanced value to their projects. This approach can mean the difference between struggling against your code base and leveraging it to enhance the team’s ability to deliver effectively.

### Definitions

This section outlines key concepts used in this article. You can skip it if you’re already knowledgeable about these topics.

#### Gradual Typing

[Gradual typing](https://en.wikipedia.org/wiki/Gradual_typing) is a feature in programming languages that allows for the incremental introduction of [type annotations](https://en.wikipedia.org/wiki/Type_signature) into a code base, enhancing its robustness. This feature is supported by several dynamic languages, including JavaScript (via [TypeScript](https://www.typescriptlang.org/)), PHP (via [Hack](https://hacklang.org/)), [Dart](https://dart.dev/), and Python (via [mypy](https://mypy.readthedocs.io/en/stable/config_file.html)). Consider the following example:

```python
import numpy as np

# without type annotations
def split_data(data, test_ratio):
    shuffled_indices = np.random.permutation(len(data))
    test_set_size = int(len(data) * test_ratio)
    test_indices = shuffled_indices[:test_set_size]
    train_indices = shuffled_indices[test_set_size:]
    return data[train_indices], data[test_indices]

# with type annotations
def split_data(data: np.ndarray, test_ratio: float) -> tuple[np.ndarray, np.ndarray]:
    shuffled_indices = np.random.permutation(len(data))
    test_set_size = int(len(data) * test_ratio)
    test_indices = shuffled_indices[:test_set_size]
    train_indices = shuffled_indices[test_set_size:]
    return data[train_indices], data[test_indices]
```

While dedicating time to assigning types to expressions might seem laborious, the benefits frequently surpass the costs. This is particularly relevant for MLOps code bases, which often manage large, untyped structures like DataFrames or AI/ML models. Utilizing dataframe schemas with tools like [Pandera](https://pandera.readthedocs.io/en/stable/) and defining model signatures with MLflow can significantly aid in object validation and the clear communication of structures. These practices not only improve code quality and maintainability but also facilitate better collaboration among developers by making the code more self-documenting and easier to understand.

#### Design Patterns

[Design patterns](https://en.wikipedia.org/wiki/Design_Patterns) are standardized solutions devised to address recurring problems in software development. For example, the [Memento pattern](https://en.wikipedia.org/wiki/Memento_pattern) enables saving the state of an entire program, while the Singleton pattern ensures a class has only one instance throughout the application, providing a single point of access to it. The example below showcases the [Decorator pattern](https://en.wikipedia.org/wiki/Decorator_pattern) for extending the capabilities of a Python function:

```python
import time
from functools import wraps

def timer(func):
    """Decorator for timing functions."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"{func.__name__} completed in {end_time - start_time} seconds")
        return result
    return wrapper

@timer
def train_model(data):
    """Simulate the training of a model."""
    time.sleep(2) # Placeholder for the actual training logic
    return "Model trained"

# Calling the decorated train model function
train_model("sample_data")
```

I wrote [an article that delves into the design patterns I find most pertinent to AI/ML code bases](https://mlops.community/become-the-maestro-of-your-mlops-abstractions/), such as the Factory, Strategy, and Adapter patterns. Although it’s impractical to explore every pattern, a wealth of literature exists on the subject. [Numerous books](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) and [articles](https://wiki.c2.com/) offer detailed guidance on understanding and choosing the most suitable design patterns for specific scenarios.

#### SOLID Principles

The [SOLID principles](https://en.wikipedia.org/wiki/SOLID) are fundamental to developing flexible and maintainable object-oriented code bases. These principles encourage the design of software in such a way that it facilitates easy maintenance and extension. Instead of confining your program to a single workflow, applying SOLID principles allows for the creation of modular code components. These components can be easily interchanged and reused throughout your project, enhancing both the scalability and robustness of the code base. SOLID is an acronym that represents five key design principles:

- ***S*ingle Responsibility Principle **— A class should have one, and only one, reason to change.
- __*O*pen/Closed Principle__ — Software entities should be open for extension, but closed for modification.
- __*L*iskov Substitution Principle__ — Objects in a program should be replaceable with instances of their subtypes without altering the correctness of that program.
- __*I*nterface Segregation Principle__ — No client should be forced to depend on methods it does not use.
- ***D*ependency Inversion Principle **— High-level modules should not depend on low-level modules. Both should depend on abstractions.

### Solutions

Let’s discuss key methods for organizing MLOps code bases and their drawbacks.

#### Just Write a Script

The prevalent approach for structuring AI/ML code bases, as often found in online examples, is straightforward: consolidate everything into a single Python script. This method is appealing for its simplicity, ensuring the code base remains concise and focused. However, this simplicity can soon prove to be inadequate for addressing the complexities of real-world applications. The typical characteristics of this approach are illustrated in the example below:

```python
# Simplistic AI/ML Python Script Example

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score

# Load and preprocess data
data = pd.read_csv('dataset.csv')
data.fillna(0, inplace=True)

# Split data
X, y = data.drop('target', axis=1), data['target']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train model
model = LogisticRegression()
model.fit(X_train, y_train)

# Evaluate model
predictions = model.predict(X_test)
accuracy = accuracy_score(y_test, predictions)
print(f"Model Accuracy: {accuracy}")
```

This script, while concise, combines data loading, preprocessing, model training, and evaluation in a single block. This approach makes it challenging to add new features, adjust preprocessing steps, or swap out the model without significant changes to the code base. It also violates SOLID principles by not being particularly well-organized for scalability, maintainability, or flexibility.

#### Functional Programming (FP)

Adopting [Functional Programming](https://en.wikipedia.org/wiki/Functional_programming) (FP) represents a significant enhancement compared to merely scripting. Rather than delineating a singular workflow for your program, FP allows for the encapsulation of code components into functions. These functions can then be orchestrated in a declarative workflow, enhancing code clarity and structure. This approach embraces core functional programming concepts, such as [high-order functions](https://en.wikipedia.org/wiki/Higher-order_function), [immutability](https://en.wikipedia.org/wiki/Immutable_object) and [pure functions](https://en.wikipedia.org/wiki/Pure_function). For instance, the example below showcases how a model can be created from a string using the two high-order level function _get_model()_ and _train_model():_

```python
from typing import Callable, Tuple

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.base import BaseEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

def load_and_preprocess_data(filepath: str, fill_na_value: float, target_name: str) -> Tuple[pd.DataFrame, pd.Series]:
    """Load and preprocess data."""
    data = pd.read_csv(filepath)
    data = data.fillna(fill_na_value)
    X = data.drop(target_name, axis=1)
    y = data[target_name]
    return X, y

def split_data(X: pd.DataFrame, y: pd.Series, test_size: float, random_state: int) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Split the data into a train and testing sets."""
    return train_test_split(X, y, test_size=test_size, random_state=random_state)

def train_model(X_train: pd.DataFrame, y_train: pd.Series, model_func: Callable[[], BaseEstimator], **kwargs) -> BaseEstimator:
    """Train the model with inputs and target data."""
    model = model_func(**kwargs)
    model.fit(X_train, y_train)
    return model

def evaluate_model(model: BaseEstimator, X_test: pd.DataFrame, y_test: pd.Series) -> float:
    """Evaluate the model with a single metric."""
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    return accuracy

def get_model(model_name: str) -> Callable[[], BaseEstimator]:
    """High-order function to select the model to train."""
    if model_name == "logistic_regression":
        return LogisticRegression
    elif model_name == "random_forest":
        return RandomForestClassifier
    else:
        raise ValueError(f"Model {model_name} is not supported.")

def run_workflow(model_name: str, model_kwargs: dict, filepath: str, fill_na_value: float, target_name: str, test_size: float, random_state: int) -> None:
    """Orchestrate the training workflow."""
    X, y = load_and_preprocess_data(filepath, fill_na_value, target_name)
    X_train, X_test, y_train, y_test = split_data(X, y, test_size, random_state)
    model_func = get_model(model_name)
    model = train_model(X_train, y_train, model_func, **model_kwargs)
    evaluate_model(model, X_test, y_test)

# Example usage
run_workflow(
    filepath='dataset.csv',
    fill_na_value=0.0,
    target_name='target',
    test_size=0.2,
    random_state=42,
    model_name='random_forest',  # Or 'logistic_regression'
    model_kwargs={'n_estimators': 30},
)
```

Functional programming strikes a great balance between simplicity and power, but it faces a significant challenge in Python. Python doesn’t support advanced functional programming concepts as well as languages like Haskell or Clojure do. Although you can write functions and use libraries like [Toolz](https://github.com/pytoolz/toolz) or [Fn.py](https://github.com/kachayev/fn.py), it’s not straightforward to use advanced techniques such as [monads](https://en.wikipedia.org/wiki/Monad_%28functional_programming%29), [currying](https://en.wikipedia.org/wiki/Currying), or [persistent data structures](https://en.wikipedia.org/wiki/Persistent_data_structure). Additionally, Python primarily relies on [subtyping](https://en.wikipedia.org/wiki/Subtyping) for [polymorphism](https://en.wikipedia.org/wiki/Polymorphism_%28computer_science%29), which isn’t as compatible with functional programming as [ad-hoc](https://en.wikipedia.org/wiki/Ad_hoc_polymorphism) or [parametric polymorphism](https://en.wikipedia.org/wiki/Parametric_polymorphism). Despite my wish for Python to lean more towards functional programming, trying to fully adopt this paradigm in Python might be a frustrating experience.

#### Object-Oriented Programming (OOP)

[Object-Oriented Programming](https://en.wikipedia.org/wiki/Object-oriented_programming) (OOP) is an excellent way to use SOLID principles in Python. Python fully supports OOP concepts, making it easy to work with. Additionally, many online tools and frameworks like [scikit-learn](https://scikit-learn.org/) and [pandas](https://pandas.pydata.org/) use OOP in their APIs. An example of this is defining a Model base class with the ABC module, which is then extended by two subclasses: _RandomForestModel_ and _KerasBinaryClassifier_. A _ModelFactory_ can select and configure the appropriate model based on external inputs.

```python
from abc import ABC, abstractmethod
from typing import Tuple, Type

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.base import BaseEstimator
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense

class Model(ABC):
    """Abstract base class for models."""
    @abstractmethod
    def train(self, X_train: pd.DataFrame, y_train: pd.Series) -> None:
        pass

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> pd.Series:
        pass

class RandomForestModel(Model):
    """Random Forest Classifier model."""
    def __init__(self, n_estimators: int = 20, max_depth: int = 5) -> None:
        self.model = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth)

    def train(self, X_train: pd.DataFrame, y_train: pd.Series) -> None:
        self.model.fit(X_train, y_train)

    def predict(self, X: pd.DataFrame) -> pd.Series:
        return self.model.predict(X)

class KerasBinaryClassifier(Model):
    """Simple binary classification model using Keras."""
    def __init__(self, input_dim: int, epochs: int = 100, batch_size: int = 32) -> None:
        self.epochs = epochs
        self.batch_size = batch_size
        self.model = Sequential([
            Dense(64, activation='relu', input_shape=(input_dim,)),
            Dense(1, activation='sigmoid')
        ])
        self.model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    def train(self, X_train: pd.DataFrame, y_train: pd.Series) -> None:
        self.model.fit(X_train, y_train, epochs=self.epochs, batch_size=self.batch_size)

    def predict(self, X: pd.DataFrame) -> pd.Series:
        predictions = self.model.predict(X)
        return (predictions > 0.5).flatten()

class ModelFactory:
    """Factory to create model instances."""
    @staticmethod
    def get_model(model_name: str, **kwargs) -> Model:
        # Assume all model classes are defined in the global scope.
        model_class = globals()[model_name]
        return model_class(**kwargs)

class Workflow:
    """Main workflow class for model training and evaluation."""
    def run_workflow(self, model_name: str, model_kwargs: dict, filepath: str, fill_na_value: float, target_name: str, test_size: float, random_state: int) -> None:
        X, y = self.load_and_preprocess_data(filepath, fill_na_value, target_name)
        X_train, X_test, y_train, y_test = self.split_data(X, y, test_size, random_state)
        model = ModelFactory.get_model(model_name, **model_kwargs)
        model.train(X_train, y_train)
        accuracy = self.evaluate_model(model, X_test, y_test)
        print(f"Model Accuracy: {accuracy}")

    def load_and_preprocess_data(self, filepath: str, fill_na_value: float, target_name: str) -> Tuple[pd.DataFrame, pd.Series]:
        """Load and preprocess data."""
        data = pd.read_csv(filepath)
        data = data.fillna(fill_na_value)
        X = data.drop(target_name, axis=1)
        y = data[target_name]
        return X, y

    def split_data(self, X: pd.DataFrame, y: pd.Series, test_size: float, random_state: int) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """Split the data into a train and testing sets."""
        return train_test_split(X, y, test_size=test_size, random_state=random_state)

    def evaluate_model(self, model: Model, X_test: pd.DataFrame, y_test: pd.Series) -> float:
        """Evaluate the model with a single metric."""
        predictions = model.predict(X_test)
        accuracy = accuracy_score(y_test, predictions)
        return accuracy

# Example usage
workflow = Workflow()
workflow.run_workflow(
    filepath='dataset.csv',
    fill_na_value=0.0,
    target_name='target',
    test_size=0.2,
    random_state="42",
    model_name='RandomForestModel',  # Or 'KerasBinaryClassifier'
    model_kwargs={'n_estimators': 30},
)
```

This code structure is often seen in well-developed MLOps projects, but it has its issues. Firstly, it lacks input and output validation at startup, leading to potential errors like mistaking a string for an integer in the _random_state_ input. Secondly, implementing a design pattern like the ModelFactory class can be complex and hard for beginners to use. To overcome these problems, I suggest using Pydantic to streamline the design and enhance the code’s reliability.

### Pydantic and ABC

[Pydantic](https://docs.pydantic.dev/latest/) is a powerful tool for creating and validating objects, ensuring that data fits your specifications. On the other hand, [Python’s Abstract Base](https://docs.python.org/3/library/abc.html) Classes (ABC) allow you to define reusable code interfaces, setting a blueprint for others to follow. Let’s dive into how these solutions can be used effectively.

#### Object Validation

Pydantic primarily focuses on [object validation](https://docs.pydantic.dev/latest/why/#type-hints). **By adding type annotations to your class attributes, you can ensure your inputs are checked right when your program starts**. This is especially useful in MLOps, where incorrect inputs can disrupt lengthy training sessions and waste valuable resources.

```python
from typing import Optional

from pydantic import BaseModel, Field

class RandomForestClassifierModel(BaseModel):
    n_estimators: int = Field(default=100, gt=0)
    max_depth: Optional[int] = Field(default=None, gt=0, allow_none=True)
    random_state: Optional[int] = Field(default=None, gt=0, allow_none=True)

model = RandomForestClassifierModel(n_estimators=120, max_depth=5, random_state=42)
```

#### Discriminated Union

The [Discriminated Union](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions) feature in Pydantic is a standout tool. **This feature lets you choose the class within a Union type by using a specific attribute (like KIND)** and validates that class with its particular attributes. With [Pydantic’s serialization abilities](https://docs.pydantic.dev/latest/why/#serialization), you can use this pattern as a streamlined alternative to the traditional Factory pattern, avoiding a lot of repetitive code.

```python
from typing import Literal, Union

from pydantic import BaseModel, Field


class Model(BaseModel):
    KIND: str


class RandomForestModel(Model):
    KIND: Literal["RandomForest"]
    n_estimators: int = 100
    max_depth: int = 5
    random_state: int = 42


class SVMModel(Model):
    KIND: Literal["SVM"]
    C: float = 1.0
    kernel: str = "rbf"
    degree: int = 3


# Union of all model configurations
ModelKind = Union[RandomForestModel, SVMModel]


class Job(BaseModel):
    model: ModelKind = Field(..., discriminator="KIND")


# initialize a job from a configs
config = {
    "model": {
        "KIND": "RandomForest",
        "n_estimators": 100,
        "max_depth": 5,
        "random_state": 42,
    }
}
job = Job.model_validate(config)
```

#### Abstract Base Classes

[Python’s Abstract Base Classes](https://docs.python.org/3/library/abc.html) (ABC) enhance MLOps code by supporting the SOLID principles. **Think of it as ensuring that different pieces fit together perfectly, like matching puzzle pieces**. In the example below, we create a Model class and two subclasses: RandomForestModel and SVMModel. These subclasses align with the base class shape, allowing them to be used interchangeably without issues.

```python
from typing import Literal, Union
from abc import ABC, abstractmethod

import pandas as pd
from pydantic import BaseModel, Field


class Model(BaseModel, ABC):
    KIND: str

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.DataFrame) -> None:
        pass

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        pass


class RandomForestModel(Model):
    KIND: Literal["RandomForest"]
    n_estimators: int = 100
    max_depth: int = 5
    random_state: int = 42

    def fit(self, X: pd.DataFrame, y: pd.DataFrame) -> None:
        print("Fitting RandomForestModel...")

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        print("Predicting with RandomForestModel...")
        return pd.DataFrame()


class SVMModel(Model):
    KIND: Literal["SVM"]
    C: float = 1.0
    kernel: str = "rbf"
    degree: int = 3

    def fit(self, X: pd.DataFrame, y: pd.DataFrame) -> None:
        print("Fitting SVMModel...")

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        print("Predicting with SVMModel...")
        return pd.DataFrame()

# Union of all model configurations
ModelKind = Union[RandomForestModel, SVMModel]

class Job(BaseModel):
    model: ModelKind = Field(..., discriminator="KIND")

    def run(self) -> pd.DataFrame:
        X_train, X_test, y_train = ..., ..., ...
        self.model.fit(X=X_train, y=y_train)
        predictions = self.model.predict(X=X_test)
        return predictions


# initialize a job from a configs
config = {
    "model": {
        "KIND": "RandomForest",
        "n_estimators": 100,
        "max_depth": 5,
        "random_state": 42,
    }
}
job = Job.model_validate(config)
job.run()
```

### Limitations

While Pydantic and Python’s ABC greatly simplify the creation of SOLID MLOps code bases, they also pose several limitations. Let’s explore those in this section.

#### Open/Closed Principle

SOLID consists of five main principles, with Pydantic and Python’s ABC aiding in three: the Liskov Substitution Principle, Interface Segregation Principle, and Dependency Inversion Principle. They serve as practical tools in these areas, while the Single Responsibility Principle acts as a design guideline for developers.

However, Pydantic and Python’s ABC don’t directly support the [Open/Closed Principle](https://en.wikipedia.org/wiki/Open%E2%80%93closed_principle). Specifically, Pydantic’s use of Tagged Unions encourages concrete class unions (like Union\[RandomForestModel, SVMModel\]) over abstract class usage (such as Model), diverging from traditional object-oriented practices. Although this approach might seem limiting, the practical benefits often outweigh the constraints, especially for applications not intended as reusable libraries. Nonetheless, you can adjust by redefining the type union in your application to fit your needs.

#### ABC vs Protocol

Python offers two ways to define code interfaces: [Abstract Base Classes](https://docs.python.org/3/library/abc.html) (ABC), which use [Nominal Typing](https://en.wikipedia.org/wiki/Nominal_type_system), and [Protocol](https://peps.python.org/pep-0544/), which uses [Structural Typing](https://en.wikipedia.org/wiki/Structural_type_system). Nominal Typing relies on class hierarchies to define relationships clearly, such as a RandomForestModel being a type of Model, making connections between classes explicit. On the other hand, Protocol is at the heart of Python’s [duck typing](https://realpython.com/lessons/duck-typing/) philosophy. It allows any class that implements certain methods to be compatible, even without an explicit declaration, meaning a RandomForestModel just needs to act like a Model to be considered one.

While Protocols can replace ABCs in some cases, their use is less straightforward with Pydantic. Pydantic’s requirement for concrete class unions makes the less explicit nature of Protocols less beneficial. Moreover, incorporating default methods into an abstract class is simpler than setting up similar functionalities with Protocols.

### Conclusions

This article explored how Pydantic and Python’s ABC can streamline implementing SOLID principles in your projects, providing a simpler, more elegant approach. **With Pydantic, MLOps developers can enjoy automatic class initialization and object validation, while Python’s ABC offers robust abstraction capabilities**. This combination allows developers to concentrate on the core logic of their programs instead of getting bogged down with custom factories and validators.

For those interested in seeing Pydantic and Python’s ABC applied in real-world MLOps, check out this GitHub repository: [https://github.com/fmind/mlops-python-package](https://github.com/fmind/mlops-python-package). It not only demonstrates these concepts but also delves into [code linting](https://en.wikipedia.org/wiki/Lint_%28software%29) and [unit testing](https://en.wikipedia.org/wiki/Unit_testing).

While I’ve found Pydantic and Python’s ABC to be highly effective for MLOps development, the quest for even simpler and more powerful solutions continues. I envision a [declarative paradigm](https://en.wikipedia.org/wiki/Declarative_programming) for MLOps, akin to what [Kubernetes](https://kubernetes.io/) offers for cloud infrastructure or [Ludwig](https://twitter.com/ludwig_ai) for deep learning. Such an approach would allow data scientists to focus on configurations, while ML engineers could concentrate on rolling out new features. But let’s save that discussion for another time. For now, march forward, and aim to be as SOLID as a rock!

![Make your Python code base rock SOLID!](/static/img/articles/make-your-mlops-code-base-solid-with-pydantic-and-pythons-abc/02.webp)

Make your Python code base rock SOLID!
