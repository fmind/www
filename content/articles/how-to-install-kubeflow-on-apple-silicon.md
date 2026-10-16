+++
title = "How to install Kubeflow Pipelines v2 on Apple Silicon"
description = "Kubeflow Pipelines (KFP) is a powerful platform for building machine learning pipelines at scale with Kubernetes."
date = "2022-09-24"
tags = ["Cloud", "Guide"]
slug = "how-to-install-kubeflow-on-apple-silicon"
syndicated = "https://medium.com/@fmind/how-to-install-kubeflow-on-apple-silicon-3565db8773f3"
draft = false
+++

**Kubeflow Pipelines (KFP) is a powerful platform for building machine learning pipelines at scale with Kubernetes**. The platform is well supported on major cloud platforms such as GCP ([Vertex AI Pipelines](https://cloud.google.com/vertex-ai/docs/pipelines/introduction)) or AWS ([Kubeflow on AWS](https://awslabs.github.io/kubeflow-manifests/)). However, installing KFP on Apple Silicon (macOS 12.5.1 with Apple M1 Pro) proved to be more challenging than I imagined. Thus, I wanted to share my experience and tips to install KFP as easily as possible on your shiny Mac.

**In this article, I present 4 steps to install Kubeflow on Apple Silicon**, using [Rancher Desktop](https://rancherdesktop.io/) for setting up Docker/Kubernetes. In the end, I list the problems I encountered during the installation of Kubeflow Pipelines.

![How to install Kubeflow Pipelines v2 on Apple Silicon](/static/img/articles/how-to-install-kubeflow-on-apple-silicon/cover.webp)

### Step 1: Install Rancher Desktop to setup Kubernetes

[**Rancher Desktop**](https://rancherdesktop.io/) **is the most friendly solution I found to install Docker and Kubernetes**. While Docker Desktop is also a popular option, this solution now has a significant price tag for companies with more than 250 employees OR \$10 million in annual revenue.

Once you install Rancher Desktop, you need to configure it using the startup window below. Select the stable version of Kubernetes and let Rancher Desktop configure the path automatically. In this case, we use containerd [as this is the default container runtime for Kubernetes](https://blog.tilt.dev/2022/03/04/rancher-desktop-container-runtimes.html).

![How to install Kubeflow Pipelines v2 on Apple Silicon](/static/img/articles/how-to-install-kubeflow-on-apple-silicon/02.webp)

I also recommend you to adjust the \# CPUs and the Memory (GB) in `Preferences > Virtual Machine` to avoid Out of Memory errors (OOM).

**You should now be able to access the** **`kubectl`** **command in your terminal**. If not, check that your PATH environment variable includes `$HOME/.rd/bin` where Rancher Desktop binaries are installed by default.

### Step 2 : Install Kubeflow Pipelines

The official instructions to install Kubeflow Pipelines are available on the [documentation website](https://www.kubeflow.org/docs/components/pipelines/v1/installation/localcluster-deployment/#deploying-kubeflow-pipelines) for KFP v1. You can also find the latest instructions on [Kubeflow Pipelines GitHub repository](https://github.com/kubeflow/pipelines/tree/58052eafc10d42dcbd3ab38abf5c944d25af0e4b/manifests/kustomize) for KFP v2. **As you can see, there is no easy one-click solution available at the time, but we can easily adapt the instructions.**

You need to make two choices for installing Kubeflow Pipelines:

- **The version of KFP (KFP_VERSION)**: We select the latest v2 version (v2.0.0b4) for the installation. This is a beta release at the time of this writing, but I found this version stable enough for my use case.
- **The platform for KFP (KFP_PLATFORM)**: This configuration defines the Argo Workflow execution engine to choose from. I select the new emissary platform ([platform-agnostic-emissary](https://github.com/kubeflow/pipelines/tree/58052eafc10d42dcbd3ab38abf5c944d25af0e4b/manifests/kustomize/env/platform-agnostic-emissary "platform-agnostic-emissary")) that [is now shipped by default in the new versions of KFP](https://www.kubeflow.org/docs/components/pipelines/v1/installation/choose-executor/).

&nbsp;

```bash
# set the variables for the installation
KFP_PLATFORM=platform-agnostic-emissary
KFP_VERSION=2.0.0b4

# start the installation using kubectl apply
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$KFP_VERSION"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/$KFP_PLATFORM?ref=$KFP_VERSION"
```

The last command may take several minutes to complete, as Kubernetes needs to download the required container images and create the pods for Kubeflow Pipelines. You can monitor the deployment happening in the `kubeflow` namespace using this command:

```bash
kubectl get pods -n kubeflow --watch
```

**Once all Kubeflow Pipelines Pods have the RUNNING Status, you can move to the next step**.

![How to install Kubeflow Pipelines v2 on Apple Silicon](/static/img/articles/how-to-install-kubeflow-on-apple-silicon/03.webp)

### Step 3: Port Forwarded

**We need to forward the port of KFP UI to your system to access the main dashboard from your browser.** To do so, set a port forward from the `ml-pipeline-ui` Pod to a port on your machine (e.g., 8443 in the example below).

```bash
kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8443:80
```

**You should now be able to access Kubeflow Pipelines at this address:** [**http://localhost:8443/#/pipelines**](http://localhost:8443/#/pipelines)

![How to install Kubeflow Pipelines v2 on Apple Silicon](/static/img/articles/how-to-install-kubeflow-on-apple-silicon/04.webp)

You can see in the screenshot above the pipelines shipped by default with Kubeflow Pipelines.

### Step 4: Run a Pipeline

**To ensure the system is working properly, we are going to run the pipelines available by default on a new installation**. As a reminder, a KFP Pipeline is a Directed Acyclic Graph (DAG) of components that generates outputs from the inputs and parameters given. The screenshot below shows the structure of the \[Demo\] XGBoost — Iterative model training pipeline.

![Demo: XGBoost — Iterative model training pipeline](/static/img/articles/how-to-install-kubeflow-on-apple-silicon/05.webp)

I tried all the pipelines available, but some of them had issues that do not seem related to the installation procedure:

- 🛑 **\[Demo\] XGBoost — Iterative model training**: the container that trains the model (Xgboost train) does not include the CMake utility.
- 🛑 **\[Demo\] TFX — Taxi prediction model training**: the pipeline only works on GCP as indicated in the description of the pipeline.

![How to install Kubeflow Pipelines v2 on Apple Silicon](/static/img/articles/how-to-install-kubeflow-on-apple-silicon/06.webp)

### (Optional) What went wrong

This guide was written after many trials and errors. You can find below the issues I encountered during the installation of Kubeflow Pipelines v2.

- **Constant ErrImagePull and ImagePullBackoff during installation**: I was not able to install KFP with the docker (moby) engine because of this error. One workaround is to connect directly to the Cluster Node and pull the image directly to fix this error:

&nbsp;

```bash
# open a shell to the node executing your pods
rdctl shell
# install the required container images manually
docker pull ...
```

- **Slow UI with Rancher Desktop port forwarding**: Rancher Desktop provides a GUI to set up port forwarding. However, the KFP UI was not responsive when I follow this method.

![How to install Kubeflow Pipelines v2 on Apple Silicon](/static/img/articles/how-to-install-kubeflow-on-apple-silicon/07.webp)

- **Solutions not compatible with Apple Silicon**: other alternatives to Rancher Desktop like [minikube](https://minikube.sigs.k8s.io/docs/start/) and [kind](https://kind.sigs.k8s.io/) didn’t work on my system (although I did not investigate these issues further).

### Conclusions

While Kubeflow Pipelines is a nice system to use out of the box on Cloud platforms, I find its installation cumbersome for local development. I hope this guide will help you set up KFP on your system, and create amazing machine learning models!

Happy Artificial Intelligence ✌️!
