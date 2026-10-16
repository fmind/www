+++
title = "Deploying AI Agents in the Enterprise using ADK and Google Cloud"
description = "Learn to deploy AI agents in the enterprise using ADK \u0026 Google Cloud. We compare Cloud Run \u0026 Vertex AI for secure, scalable AgentOps."
date = "2025-08-10"
tags = ["Agent", "Cloud"]
slug = "deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud"
syndicated = "https://medium.com/@fmind/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud-b49e7eda3b41"
draft = false
+++

### **Deploying AI Agents in the Enterprise without** Losing **your Humanity u**sing ADK and Google Cloud

The excitement around AI agents is palpable. From automating complex workflows to providing personalized experiences, the potential is enormous. But as Data Scientists and developers rush to build proof-of-concepts, a significant hurdle emerges when it’s time to deploy these agents within a real-world organization.

I’ve recently been tackling these exact challenges with my customers. The goal is clear: find solutions that are simple, powerful, and accessible for the whole team. But moving from a local demo to a production-ready agent involves navigating the labyrinth of enterprise IT.

AgentOps is uniquely challenging because it combines the inherent complexity of non-deterministic systems (like Machine Learning) with the stringent requirements of enterprise security and the need to expose these applications securely to a wide audience.

In this article, we’ll explore the challenges of deploying agents in a corporate environment and dive into practical strategies using [Google Cloud Platform (GCP)](https://cloud.google.com/gcp?authuser=1), based on the findings and code in my [GitHub Repository](https://github.com/fmind/search-agent/tree/main/search_agent).

![Source: Gemini App](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/cover.webp)

Source: Gemini App

### The AgentOps Challenge: Bridging the Gap Between POC and Production 🛡️

Deploying an application in an organization isn’t just about making the code run on a server. It’s about integrating it seamlessly and securely into the existing IT ecosystem. This means considering:

- **Networking:** Your agent likely needs to live within a [Virtual Private Cloud (VPC)](https://cloud.google.com/vpc/docs/overview?authuser=1), behind firewalls, and potentially protected by a [Web Application Firewall (WAF)](https://cloud.google.com/security/products/waf?authuser=1).
- **Authentication Mechanisms:** How do users access the agent? Organizations often use complex identity providers (IdPs) leveraging protocols like [OIDC (OpenID Connect)](https://openid.net/connect/) or [SAML (Security Assertion Markup Language)](https://en.wikipedia.org/wiki/Security_Assertion_Markup_Language).
- **Security and Risk:** Exposing an unauthenticated application on the public internet is a recipe for disaster, potentially leaking sensitive data or allowing unauthorized access to internal systems.

A critical aspect of AgentOps is **identity propagation**. If an agent is designed to access a user’s resources (like reading their emails or calendar), it must be able to verify _who_ the user is. This requires robust authentication that connects the user’s identity from the front-end all the way through to the agent’s backend logic, often managed through systems like [IAM (Identity and Access Management)](https://cloud.google.com/iam/docs/overview?authuser=1).

Furthermore, a production-ready agent needs multiple exposition mechanisms:

1. [**A Web UI**](https://github.com/google/adk-web) **:** For quick testing and human interaction.
2. [**An API Endpoint**](https://google.github.io/adk-docs/get-started/testing/) **:** To integrate the agent into other applications and services.
3. [**Agent-to-Agent (A2A) Protocol**](https://google.github.io/adk-docs/a2a/) **:** For interoperability and complex multi-agent systems.

![Source: https://codelabs.developers.google.com/intro-a2a-purchasing-concierge#0](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/02.webp)

Source: [https://codelabs.developers.google.com/intro-a2a-purchasing-concierge#0](https://codelabs.developers.google.com/intro-a2a-purchasing-concierge#0)

Achieving all three securely is the core of the AgentOps exposition challenge.

### Exploring Deployment Strategies on GCP 🚀

Google Cloud provides both powerful models (like [Gemini](https://deepmind.google/technologies/gemini/), accessed via [Vertex AI](https://cloud.google.com/vertex-ai?authuser=1)) and robust infrastructure solutions. We explored several paths to deploy a sample search agent, evaluating them based on flexibility, security, and ease of use.

The architecture diagram below illustrates the two main paths I evaluated for secure deployment on GCP:

![Architecture Diagram with the 2 Deployment Paths: Vertex AI Agent Engine and Cloud Run (Source: fmind.dev)](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/03.webp)

Architecture Diagram with the 2 Deployment Paths: Vertex AI Agent Engine and Cloud Run (Source: fmind.dev)

The diagram highlights how clients (either end-users via a browser or services/other agents via API calls) interact with the agent logic. Both paths rely on [GCP’s IAM](https://cloud.google.com/security/products/iam) to manage permissions, but they handle exposition and authentication differently.

- **Path 1:** [**Cloud Run**](https://cloud.google.com/run?hl=en) **(Flexible):** This approach deploys the agent in a containerized environment. It uses [Google IAP](https://cloud.google.com/security/products/iap?hl=en) (Identity-Aware Proxy) as a gatekeeper to authenticate all incoming traffic, securing the Web UI and the API/A2A endpoints uniformly. This provides maximum control and versatility.
- **Path 2:** [**Vertex AI Agent Engine**](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview) **(Opinionated):** This approach uses a managed service specifically designed for agents. Authentication is handled by the service’s API gateway, granting access to clients with the appropriate IAM roles, but it is limited to API exposition.

In our example we are going to deploy [a simple search agent](https://github.com/fmind/search-agent/blob/main/search_agent/agent.py) with ADK:

```python
"""A simple search agent."""

# %% IMPORTS

from google.adk.agents import Agent
from google.adk.tools import google_search

# %% AGENTS

root_agent = Agent(
    name="search_agent",
    model="gemini-2.5-flash",
    description="Agent to answer questions using Google Search.",
    instruction="You are an expert researcher. You always stick to the facts.",
    # use the builtin google_search tool from ADK
    tools=[google_search],
)
```

Let’s dive into the details, pros, and cons of these approaches, as well as other alternatives.

#### Option 1: The Wild West — Unauthenticated Internet Deployment 🌵

The easiest path is often the most dangerous. Cloud providers make it simple to deploy an application and expose it to the public internet without authentication.

**Verdict:** While fast for development, this is generally unacceptable for enterprise deployment unless stringent security practices (both internal application security and external network security) are rigorously implemented and audited. We won’t explore this further in the code repository, as our focus is on secure deployment.

#### Option 2: The Opinionated Path — Vertex AI Agent Engine 🤖

[Vertex AI Agent Engine](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview?authuser=1) offers a managed, opinionated approach to deploying agents (Path 2 in the architecture diagram).

```justfile
# deploy to agent engine
deploy-agent-engine:
    uv run adk deploy agent_engine --project=$GOOGLE_CLOUD_PROJECT --region=$GOOGLE_CLOUD_LOCATION --staging_bucket=$STAGING_BUCKET --trace_to_cloud \
        --display_name={{AGENT}} --description={{AGENT}} {{env('AGENT_ENGINE_ID', '') && "--agent_engine_id=" + env('AGENT_ENGINE_ID')}} {{AGENT}}
```

![List of Agents on Vertex AI Agent Engine](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/04.webp)

List of Agents on Vertex AI Agent Engine

**Pros:**

- **Out-of-the-box:** Streamlines the deployment process.
- **Monitoring:** Provides a dedicated console dashboard to monitor agent performance and sessions.
- **Authentication:** Offers relatively easy mechanisms to [authenticate](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/manage/access?authuser=1) and use the agent from other applications via REST API or the [Python SDK](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/use/adk?authuser=1#vertex-ai-sdk-for-python).

![Search Agent running on Vertex AI Agent Engine](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/05.webp)

Search Agent running on Vertex AI Agent Engine

**Cons:**

- **Flexibility:** You cannot deploy a custom Web UI or an A2A endpoint directly; it only exposes a REST API.
- **Control:** Less control over the underlying resources.
- **Pricing:** The [pricing model](https://cloud.google.com/vertex-ai/pricing?authuser=1#agent_engine) per hardware is less flexible compared to request-based solutions.

**Verdict:** A great starting point for deploying API-based agents, but a lack of flexibility for UI and A2A exposition. As the product becomes more mature, it should become the go-to option on GCP.

#### Option 3: The Sweet Spot — Cloud Run 🏃‍♀️

[Cloud Run](https://cloud.google.com/run/docs/overview/what-is-cloud-run?authuser=1) is Google Cloud’s serverless container platform, and it emerged as the best trade-off for deploying agents today (Path 1 in the architecture diagram).

```justfile
# deploy to cloud run
deploy-cloud-run:
    # when asked "Allow unauthenticated invocations to [search-agent] (y/N)?", answer "n"
    adk deploy cloud_run --project=$GOOGLE_CLOUD_PROJECT --region=$GOOGLE_CLOUD_LOCATION --trace_to_cloud \
    --service_name={{replace(AGENT, '_', '-')}} --app_name={{AGENT}} --with_ui --a2a {{AGENT}}
```

![List of Services deployed on Cloud Run](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/06.webp)

List of Services deployed on Cloud Run

**Pros:**

- **Simplicity:** Cloud Run is incredibly easy and convenient to use, often requiring just a single CLI command for deployment.
- **Total Control:** You manage everything, from the hardware used (CPU, GPU) to scalability settings and exposition mechanisms.
- **Versatility:** You can expose a Web UI, an API server, and an A2A endpoint all from the _same_ instance, simplifying maintenance.
- **Pricing:** The [pricing](https://cloud.google.com/run/pricing?hl=en&authuser=1) is highly flexible — you pay per resource consumed, and it can scale down to zero.
- **Ecosystem:** Cloud Run integrates seamlessly with other GCP services and provides excellent operational features: Dashboards, Logging, Revision Management, SLOs, and Alerting.

![Agent running on Cloud Run](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/07.webp)

Agent running on Cloud Run

**Verdict:** Currently the best option. It provides the necessary control to implement robust security and versatile exposition while maintaining the ease of use of a serverless platform. The [ADK documentation](https://google.github.io/adk-docs/deploy/cloud-run/) also provides guidance on this path.

#### Option 4: The Future — AgentSpace 🔮

The main problem of AgentOps, as discussed, is exposition and identity management. This is where [Google AgentSpace](https://cloud.google.com/products/agentspace?hl=en&authuser=1) comes in.

AgentSpace is an intranet search, AI assistant, and agentic platform. On top of that, it can solve our challenges by adding an exposition and identity layer on top of Vertex AI Agent Engine, complementing it perfectly. Over time, it might become the best solution for integrating agents while developers can focus on building the backend systems.

![Integration of Agent Engine and AgentSpace: https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/08.webp)

Integration of Agent Engine and AgentSpace: [https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview)

**Verdict:** AgentSpace and Vertex AI Engine are the future integrated solution for streamlined, secure agent deployment on GCP. As of August 2025, these solutions need to mature a bit more to catch up with the flexibility offered by Cloud Run.

### Deep Dive: Securing Agents with IAP on Cloud Run 🔒

When choosing Cloud Run, we still need a way to secure it. We want a single solution that provides authentication for the Web UI, the API, and A2A communication, ensuring we know who (or what) is interacting with our agent.

While options like implementing custom authentication within the application using OIDC or SAML exist, they add significant complexity to the codebase.

For the repository, we chose Google’s [**Identity-Aware Proxy (IAP)**](https://cloud.google.com/iap/docs/concepts-overview?authuser=1).

#### Why IAP?

IAP is a [zero-trust](https://cloud.google.com/beyondcorp?authuser=1) access solution that allows you to manage access to applications running on GCP. It acts as a gatekeeper (as shown in Path 1 of the architecture diagram), verifying user identity and context before authorizing access to the application.

- **Simplicity:** It works great out of the box without requiring complex changes to the application code.
- **Versatility:** It provides authentication both for end-users (via browser redirects) and services (via headers).
- **Identity Propagation:** IAP securely passes the authenticated user’s identity to the application, which is key for AgentOps to associate a user with their resources.

#### End-User Authentication (Web UI) 👩‍💻

Configuring IAP for a Cloud Run service is straightforward. You enable IAP on the service and define which principals (users, groups or domains) are allowed access via IAM on the Security Tab.

![Identity Access Proxy (IAP) Management on Cloud Run](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/09.webp)

Identity Access Proxy (IAP) Management on Cloud Run

When a user tries to access the Web UI, IAP intercepts the request, authenticates the user (usually via Google Sign-In, though [external identities](https://cloud.google.com/iap/docs/external-identities?authuser=1) are supported), and grants access if authorized.

![Google Sign-In Page to Authenticate the End User](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/10.webp)

Google Sign-In Page to Authenticate the End User

![Agent Web UI with ADK after Sign-In](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/11.webp)

Agent Web UI with ADK after Sign-In

You can find more details in the [Google documentation on securing Cloud Run with IAP](https://cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run?authuser=1).

#### Service Authentication (API and A2A) 🤝

For [programmatic access](https://cloud.google.com/run/docs/authenticating/developers?authuser=1) (API calls or A2A communication), the authentication flow is different. Services typically use [service accounts](https://cloud.google.com/iam/docs/service-accounts?authuser=1) and must provide an OpenID Connect (OIDC) token (a [JWT](https://jwt.io/introduction)) in the `Authorization` header of the request.

IAP validates this token (which must be signed by Google and have the correct audience — the Cloud Run URL or IAP Client ID) before allowing the request to reach the agent.

This is crucial for secure A2A communication in the enterprise. Agents need to discover each other (often via an [Agent Card](https://github.com/fmind/search-agent/blob/main/search_agent/agent.json), as shown below) and communicate securely.

![Search Agent — Agent Card for the A2A Protocol](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/12.webp)

Search Agent — Agent Card for the A2A Protocol

To make this work, the calling agent needs to generate a valid JWT token. Here is a Python snippet demonstrating how to achieve this when calling an IAP-protected endpoint ([from the GitHub Repository User Agent](https://github.com/fmind/search-agent/blob/main/user_agent/agent.py)):

```python
"""User-facing agent that delegates search queries to a remote A2A agent."""

# %% IMPORTS

import datetime
import json
import os

import google.auth
import httpx
from google.adk.agents.llm_agent import Agent
from google.adk.agents.remote_a2a_agent import (
    AGENT_CARD_WELL_KNOWN_PATH,
    RemoteA2aAgent,
)
from google.cloud import iam_credentials_v1

# %% ENVIRONS

# URL to the Agent Card. See: https://google.github.io/adk-docs/a2a/quickstart-consuming/#how-it-works
# It's the entry point for the user-facing agent to discover and interact with the remote agent.
AGENT_CARD = os.getenv(
    "AGENT_CARD", f"http://localhost:8000/a2a/search_agent{AGENT_CARD_WELL_KNOWN_PATH}"
)
# Email of the calling GCP Service Account (SA)
# This is used to authenticate to the remote agent.
AGENT_RUN_SA = os.environ["AGENT_RUN_SA"]

# %% CLIENTS

# Authenticate to Google Cloud using the default credentials.
# This is necessary to use the IAM Credentials API to sign JWTs.
credentials, project_id = google.auth.default()
iam_client = iam_credentials_v1.IAMCredentialsClient(credentials=credentials)


def get_auth_token(url: str, exp: int = 3600) -> str:
    """Gets an auth token for a given URL with a expiry time (in seconds).

    The JWT contains the following claims:
    - aud: The audience of the token, which is the URL of the remote agent.
    - iss: The issuer of the token, which is the service account.
    - sub: The subject of the token, which is also the service account.
    - iat: The time the token was issued (issued at).
    - exp: The time the token expires (expiration time).

    Args:
        url: The URL of the remote agent to authenticate to.
        exp: The expiration time of the token in seconds.

    Returns:
        The signed JWT.
    """
    # Get the current time.
    iat = datetime.datetime.now(tz=datetime.timezone.utc)
    # Set the expiration time.
    exp = iat + datetime.timedelta(seconds=exp)
    # Create the JWT payload.
    jwt = {
        "aud": url,
        "iss": AGENT_RUN_SA,
        "sub": AGENT_RUN_SA,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
    }
    # Convert the JWT to a JSON string.
    payload = json.dumps(jwt)
    # Get the full name of the service account.
    name = iam_client.service_account_path("-", AGENT_RUN_SA)
    # Sign the JWT using the IAM Credentials API.
    response = iam_client.sign_jwt(name=name, payload=payload)
    # Return the signed JWT.
    return response.signed_jwt


class BearerAuth(httpx.Auth):
    """A custom httpx authentication class that uses a bearer token."""

    def auth_flow(self, request):
        """Adds the Authorization header to the request.

        Args:
            request: The request to add the Authorization header to.

        Yields:
            The request with the Authorization header.
        """
        # Get a new auth token for the request's URL.
        token = get_auth_token(str(request.url))
        # Add the Authorization header to the request.
        request.headers["Authorization"] = f"Bearer {token}"
        # Yield the request to httpx to be sent.
        yield request


# Create an httpx client with the custom bearer authentication.
httpx_client = httpx.AsyncClient(auth=BearerAuth(), timeout=600)

# %% AGENTS


# Create a remote A2A agent that represents the remote search agent.
# This agent will delegate calls to the remote agent's tools.
search_agent = RemoteA2aAgent(
    name="search_agent",
    agent_card=AGENT_CARD,
    description="Google Search Agent",
    httpx_client=httpx_client,
)

# Create a root agent that orchestrates the interaction with the user.
# This agent will delegate search queries to the remote search agent.
root_agent = Agent(
    name="root_agent",
    model="gemini-2.5-flash",
    instruction="You are a nice and polite agent. Deleguate search query to the search_agent.",
    sub_agents=[search_agent],
)
```

_Note: The JWT token works only for a specific audience (URL/Client ID), ensuring that a token generated for one service cannot be reused for another._

![User Agent calling the Search Agent deployed on Cloud Run using the A2A Protocol](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/13.webp)

User Agent calling the Search Agent deployed on Cloud Run using the A2A Protocol

### Conclusion: The AgentOps Gold Rush 🌟

Deploying AI agents in the enterprise is far from trivial. The intersection of machine learning’s unpredictability and the rigid requirements of corporate IT creates a unique set of challenges.

We are still in the early days of **AgentOps**. There is a pressing need for new architectures, deployment patterns, and tools to facilitate this process. I believe there will be a _gold rush_ for those with the technical prowess to build robust, secure, and scalable IT systems for agents.

This journey won’t be as easy as some might think, but leveraging powerful and flexible tools like Cloud Run and the broader Google Cloud ecosystem definitely provides a significant advantage. As we move forward, remember the K.I.S.S. principle: Keep It Simple (Stupid). Simple, well-understood solutions like Cloud Run combined with IAP can offer the best path to bringing the power of AI agents securely into the enterprise today.

_Explore the code and deployment configurations discussed in this article on my GitHub repository:_ [https://github.com/fmind/search-agent](https://github.com/fmind/search-agent)

![Source: Gemini App](/static/img/articles/deploying-ai-agents-in-the-enterprise-using-adk-and-google-cloud/14.webp)

Source: Gemini App
