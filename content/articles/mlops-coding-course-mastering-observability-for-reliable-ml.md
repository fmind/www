+++
title = "MLOps Coding Course: Mastering Observability for Reliable ML 💡"
description = "This article dives deep into the essential tools and practices for achieving comprehensive observability in your AI/ML projects."
date = "2024-07-28"
tags = ["MLOps", "Guide"]
slug = "mlops-coding-course-mastering-observability-for-reliable-ml"
draft = false
+++

In [the last blog article](https://home.mlops.community/public/blogs/mlops-coding-course-bridging-the-gap-between-data-scientists-and-machine-learning-engineers), we constructed [a robust and production-ready MLOps codebase](https://github.com/fmind/mlops-python-package). But the journey doesn’t end with deployment. The real test begins when your model encounters the dynamic and often unpredictable world of production. That’s where [**Observability**](https://mlops-coding-course.fmind.dev/7.%20Observability/index.html), the focus of [Chapter 7](https://mlops-coding-course.fmind.dev/7.%20Observability/index.html) in the [MLOps Coding Course](https://mlops-coding-course.fmind.dev/), takes center stage.

This article dives deep into the essential tools and practices for achieving comprehensive observability in your ML projects. We’ll unravel key concepts, showcase practical code examples from the accompanying [MLOps Python Package](https://github.com/fmind/mlops-python-package), and explore the benefits of integrating industry-leading solutions like [MLflow](https://mlflow.org/).

![Coin-operated telescope overlooking a coastal city and its harbor — Photo by Elisa Schmidt on Unsplash](/static/img/articles/mlops-coding-course-mastering-observability-for-reliable-ml/cover.webp)

Coin-operated telescope overlooking a coastal city and its harbor — Photo by [Elisa Schmidt](https://unsplash.com/@elisasch?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

_Note: The course is also available on the_ [_MLOps Community Learning Platform_](https://learn.mlops.community/courses/languages/mlops-coding-course/)

### Why Observability is Your ML’s Guardian Angel 😇

Deploying a model that initially shines with stellar performance only to witness its accuracy fade over time is a nightmare scenario for any ML engineer. Without observability, you’re left fumbling in the dark, trying to diagnose issues in a black box. Observability empowers you to:

- **Preempt Disaster with Proactive Monitoring:** Continuously track crucial metrics like data drift, concept drift, or model performance degradation. Set up alerts to notify you of potential issues _before_ they impact users, allowing for timely interventions.
- **Unlock the Secrets of Your Model’s Decision-Making:** Employ explainability techniques to understand feature contributions and identify potential biases. This transparency builds trust with stakeholders and ensures responsible AI practices.
- **Optimize for Peak Performance and Efficiency**: Gain deep insights into infrastructure usage and resource consumption. This knowledge allows you to pinpoint bottlenecks, optimize performance, and make data-driven decisions for cost-effective scaling.
- **Ensure Confidence and Reproducibility**: Track the lineage of data and models, meticulously documenting their journey from source to production. This practice fosters reproducibility, enabling you to recreate experiments, validate findings, and ensure consistent behavior across different environments.

### [MLflow](https://mlflow.org/): Your Observability Command Center 📡

[MLflow](https://mlflow.org/), the open-source platform we’ve come to rely on, rises to the occasion once again, providing a versatile and powerful set of tools for managing [the entire ML lifecycle](https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning). The [MLOps Coding Course](https://mlops-coding-course.fmind.dev/) leverages MLflow’s capabilities to the fullest, demonstrating how to:

**1. Guarantee** [**Reproducibility**](https://mlops-coding-course.fmind.dev/7.%20Observability/7.0.%20Reproducibility.html) **with** [**MLflow Projects**](https://mlflow.org/docs/latest/projects.html)**:**

Standardize the way you package your ML code, dependencies, and environment configurations using [MLflow Projects](https://mlflow.org/docs/latest/projects.html). This ensures consistent execution across different environments and facilitates seamless sharing and collaboration.

[**MLproject file**](https://github.com/fmind/mlops-python-package/blob/main/MLproject)**:**

```yaml
# Define the structure of your MLflow project
name: bikes
python_env: python_env.yaml
entry_points:
  main:
    parameters:
      conf_file: path
    command: "PYTHONPATH=src python -m bikes {conf_file}"
```

**2. Shine a Light on** [**Model Monitoring**](https://mlops-coding-course.fmind.dev/7.%20Observability/7.1.%20Monitoring.html) **with** [**MLflow Model Evaluation**](https://mlflow.org/docs/latest/model-evaluation/index.html)**:**

Employ [MLflow’s evaluate API](https://mlflow.org/docs/latest/model-evaluation/index.html) to compute and log a comprehensive suite of model performance metrics. Define thresholds to trigger alerts when metrics deviate from expected ranges.

[**Evaluation Job file**](https://github.com/fmind/mlops-python-package/blob/main/src/bikes/jobs/evaluations.py)**:**

```python
from bikes.core import metrics as metrics_
# Define the metrics to track
metrics = [
    metrics_.SklearnMetric(name="mean_squared_error", greater_is_better=False),
    metrics_.SklearnMetric(name="r2_score", greater_is_better=True),
]
# Define thresholds for specific metrics (optional)
thresholds = {
    "r2_score": metrics_.Threshold(threshold=0.5, greater_is_better=True) # Alert if R-squared drops below 0.5
}
```

![Model Monitoring with MLflow Model Evaluation](/static/img/articles/mlops-coding-course-mastering-observability-for-reliable-ml/02.webp)

Model Monitoring with [MLflow Model Evaluation](https://mlflow.org/docs/latest/model-evaluation/index.html)

**For data and model drift detection, integrate** tools like [Evidently](https://www.evidentlyai.com/) to automate the generation of interactive reports. Visualize data drift, model performance variations, and other critical insights, enabling you to understand and address potential issues quickly.

[**Evidently Example**](https://docs.evidentlyai.com/examples/introduction)**:**

```python
import pandas as pd
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset

# Load reference data (data used for training)
reference_data = pd.read_csv('reference.csv')
# Load current data (data the model is currently predicting on)
current_data = pd.read_csv('current.csv')
# Generate an Evidently report for data drift detection
report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=reference_data, current_data=current_data)
report.show()  # Display the interactive report in a web browser
# or
# report.save_html('my_report.html')  # Save the report as an HTML file
```

**3. Set up** [**Alerting**](https://mlops-coding-course.fmind.dev/7.%20Observability/7.2.%20Alerting.html) **for Timely Interventions:**

During development, utilize a simple alerting service based on the [Plyer](https://plyer.readthedocs.io/) library. Send instant desktop notifications to developers about significant events in the MLOps pipeline.

[**Alerting Service file**](https://github.com/fmind/mlops-python-package/blob/main/src/bikes/io/services.py)**:**

```python
from bikes.io import services

# Initialize the alerting service, enable notifications, and set application name and timeout
alerts_service = services.AlertsService(enable=True, app_name="Bikes", timeout=5)
# Within a job's run() method, send a notification when a task completes
self.alerts_service.notify(title="Training Complete", message=f"Model version: {model_version.version}")
```

For production environments, integrate with powerful platforms like [Datadog](https://www.datadoghq.com/). Datadog offers comprehensive dashboards, customizable alerts, and flexible notification channels to keep you informed.

**4. Trace the** [**Data/Model Lineage**](https://mlops-coding-course.fmind.dev/7.%20Observability/7.3.%20Lineage.html) **with** [**MLflow Dataset Tracking**](https://mlflow.org/docs/latest/tracking.html#tracking-datasets)**:**

Employ [MLflow Data API](https://mlflow.org/docs/latest/tracking/data-api.html) to meticulously track the lineage of your data, documenting its origin, transformations, and usage within your models. This creates a transparent and auditable record, essential for debugging, reproducibility, and data governance.

[**Lineage in Training Job file**](https://github.com/fmind/mlops-python-package/blob/main/src/bikes/jobs/training.py)**:**

```python
import mlflow.data.pandas_dataset as lineage

# Within a job's run() method
inputs_lineage = lineage.from_pandas(
  df=data, name=name, source=self.path, targets=targets, predictions=predictions
)
mlflow.log_input(dataset=inputs_lineage, context=self.run_config.name)
```

![Data Lineage information gathered with MLflow Data API](/static/img/articles/mlops-coding-course-mastering-observability-for-reliable-ml/03.webp)

Data Lineage information gathered with [MLflow Data API](https://mlflow.org/docs/latest/tracking/data-api.html)

**5.** [**Manage Costs and Measure Success with KPIs**](https://mlops-coding-course.fmind.dev/7.%20Observability/7.4.%20Costs-KPIs.html)**:**

The [MLOps Python Package](https://github.com/fmind/mlops-python-package) provides a practical [notebook](https://github.com/fmind/mlops-python-package/blob/main/notebooks/indicators.ipynb) demonstrating how to extract and analyze technical cost and KPI data from an [MLflow server](https://mlflow.org/docs/latest/getting-started/running-notebooks/index.html). This data empowers you to understand resource consumption patterns, identify bottlenecks, and optimize your project’s performance and budget.

![Visualize the run time of experiment runs from the MLflow Server](/static/img/articles/mlops-coding-course-mastering-observability-for-reliable-ml/04.webp)

Visualize the run time of experiment runs from the MLflow Server

**6. Open the Black Box with** [**Explainability**](https://mlops-coding-course.fmind.dev/7.%20Observability/7.5.%20Explainability.html)**:**

Integrate [SHAP (SHapley Additive exPlanations)](https://shap.readthedocs.io/en/latest/) to unveil the decision-making process of your models. Analyze feature importance scores, both globally and for individual predictions, to gain insights into model behavior, identify potential biases, and guide model improvement efforts.

[**Explain samples from Models file**](https://github.com/fmind/mlops-python-package/blob/main/src/bikes/core/models.py)**:**

```python
@T.override
def explain_samples(self, inputs: schemas.Inputs) -> schemas.SHAPValues:
    """Explain model outputs on input samples.

    Args:
        inputs (schemas.Inputs): The input data samples.
    Returns:
        schemas.SHAPValues: A dataframe containing the SHAP values for each feature.
    """
    model = self.get_internal_model()
    regressor = model.named_steps["regressor"]
    transformer = model.named_steps["transformer"]
    transformed = transformer.transform(X=inputs)
    explainer = shap.TreeExplainer(model=regressor)
    shap_values = schemas.SHAPValues(
        data=explainer.shap_values(X=transformed),
        columns=transformer.get_feature_names_out(),
    )
    return shap_values
```

![SHAP Values for explaining feature influences on data samples](/static/img/articles/mlops-coding-course-mastering-observability-for-reliable-ml/05.webp)

[SHAP Values](https://shap.readthedocs.io/en/latest/example_notebooks/overviews/An%20introduction%20to%20explainable%20AI%20with%20Shapley%20values.html#) for explaining feature influences on data samples

**7. Keep a Watchful Eye on** [**Infrastructure**](https://mlops-coding-course.fmind.dev/7.%20Observability/7.6.%20Infrastructure.html) **with** [**MLflow System Metrics**](https://mlflow.org/docs/latest/system-metrics/index.html)**:**

Enable [MLflow system metrics](https://mlflow.org/docs/latest/system-metrics/index.html) logging to capture valuable hardware performance indicators during the execution of your MLOps jobs. This data provides a window into resource utilization, helps you identify potential performance bottlenecks or issues, and enables you to make data-driven decisions regarding scaling and resource allocation.

![Collect and display System Metrics with MLflow](/static/img/articles/mlops-coding-course-mastering-observability-for-reliable-ml/06.webp)

Collect and display System Metrics with MLflow

### Conclusions

Observability is the key to unlocking the true potential of your ML solutions. The [MLOps Coding Course arms](https://mlops-coding-course.fmind.dev/) you with the knowledge and tools to build robust, insightful, and production-ready monitoring systems, ensuring your AI/ML initiatives thrive in the dynamic world of production.

Embrace the principles and practices outlined in the course, integrate powerful tools like [MLflow](https://mlflow.org/docs/latest/index.html), [Evidently](https://www.evidentlyai.com/) or [Datadog](https://www.datadoghq.com/solutions/machine-learning/), and watch your MLOps projects blossom with enhanced reliability, performance, and trustworthiness.

![Lighthouse at the end of a stone walkway on a rocky coast at dusk — Photo by Luca Bravo on Unsplash](/static/img/articles/mlops-coding-course-mastering-observability-for-reliable-ml/07.webp)

Lighthouse at the end of a stone walkway on a rocky coast at dusk — Photo by [Luca Bravo](https://unsplash.com/@lucabravo?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)
