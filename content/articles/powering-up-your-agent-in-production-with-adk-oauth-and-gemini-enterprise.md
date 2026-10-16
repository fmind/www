+++
title = "Powering Up your Agent in Production with ADK, OAuth and Gemini Enterprise"
description = "Power up your AI agent in production. Learn to deploy a secure ‘Slides Translator’ using ADK, OAuth, and Gemini Enterprise."
date = "2025-11-01"
tags = ["Agent", "Cloud"]
slug = "powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise"
syndicated = "https://medium.com/@fmind/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise-a52b0716fcba"
draft = false
+++

The promise of AI agents is immense productivity gains. But putting them into production can be a tale of two extremes: surprisingly fast or painfully slow.

The difference often hinges on the infrastructure and tooling you choose. If you attempt to build everything from scratch — creating a custom UI, managing complex authentication flows, and setting up observability — development slows down significantly. You spend more time on infrastructure than on the agent logic itself. I recently argued this point in [“The Real AI Agent Bottleneck is the Damn UI”](https://fmind.medium.com/the-real-ai-agent-bottleneck-is-the-damn-ui-90e90ee369e0).

However, with the right tools, deploying an agent can be remarkably quick.

To demonstrate how to achieve this fast route, we need a practical example. A while ago, I shared a [notebook built over lunch to translate Google Slides](https://fmind.medium.com/slides-to-translate-when-it-says-no-build-a-0-04-solution-on-your-lunch-break-3afa8bd9f6bb). It was effective but stuck in a notebook, inaccessible to my teammates.

![A hacker tinkering with a robot (Source: Gemini App)](/static/img/articles/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise/cover.webp)

A hacker tinkering with a robot (Source: Gemini App)

This article details the journey of taking that “Slides Translator” and pushing it into production as a secure, scalable agent, leveraging the right stack to bypass the usual bottlenecks. We will focus on using the [Agent Development Kit (ADK)](https://google.github.io/adk-docs/), [OAuth](https://oauth.net/2/), and [Gemini Enterprise](https://cloud.google.com/gemini-enterprise?hl=en).

The full code for this project is available on GitHub: [https://github.com/fmind/slides-translator-agent](https://github.com/fmind/slides-translator-agent)

### The Agentic Architecture

To move from a notebook to a production agent, we need an architecture that handles security, execution, and user access robustly.

![Architecture of the Slide Translator Agent from local development to production deployment (Source: fmind.dev)](/static/img/articles/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise/02.webp)

Architecture of the Slide Translator Agent from local development to production deployment (Source: fmind.dev)

The workflow is structured as follows:

1. **Local Development:** The agent logic is developed using the [Agent Development Kit (ADK)](https://google.github.io/adk-docs/) and tested locally via the [ADK Web UI](https://github.com/google/adk-web).
2. **Deployment:** The agent is deployed to the [**Vertex AI Agent Engine**](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview) on Google Cloud Platform.
3. **Production Access:** Users interact with the agent through the [**Gemini Enterprise Web UI**](https://cloud.google.com/gemini-enterprise?hl=en).
4. **Execution and Security:** The Agent Engine manages the execution. It uses [**OAuth**](https://oauth.net/2/) for secure authorization, interacts with [**Google APIs**](https://developers.google.com/apis-explorer) **(Drive and Slides)** on the user’s behalf, and utilizes [**Gemini Models**](https://ai.google.dev/gemini-api/docs/models) for the translation.

### ADK and the Power of OAuth

The [Agent Development Kit (ADK)](https://github.com/google/adk-python) provides a great set of features to handle everything you need for building agents. In this specific use case, I focused on its ability to handle **OAuth**, to let the user grant access to their slides and drive.

![Overview of Google ADK and Vertex AI Agent Engine (Source: https://cloud.google.com/agent-builder/agent-engine/overview )](/static/img/articles/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise/03.webp)

Overview of Google ADK and Vertex AI Agent Engine (Source: [https://cloud.google.com/agent-builder/agent-engine/overview](https://cloud.google.com/agent-builder/agent-engine/overview))

In the notebook prototype, authentication relied on local credentials. This is not suitable for a production agent that needs to access the _user’s_ specific files. The agent must act on behalf of the user, requiring their explicit permission.

### Why OAuth?

[OAuth 2.0](https://oauth.net/2/) provides excellent security guarantees and granularity. It allows users to grant specific permissions (scopes) without sharing their passwords with the agent. In this case, we need access to the [Google Drive API](https://developers.google.com/drive/api?authuser=1) (to copy the presentation) and the [Google Slides API](https://developers.google.com/slides/api?authuser=1) (to read and write slide content).

While OAuth is not an easy concept to grasp for newcomers, it’s a key component to provide more security in enterprise applications.

![OAuth flow for a tool with Google ADK (Source: https://google.github.io/adk-docs/tools/authentication/ )](/static/img/articles/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise/04.webp)

OAuth flow for a tool with Google ADK (Source: [https://google.github.io/adk-docs/tools/authentication/](https://google.github.io/adk-docs/tools/authentication/))

### Configuration

To make this work, an OAuth Client ID must be configured in the Google Cloud Console: [https://console.cloud.google.com/auth/clients](https://console.cloud.google.com/auth/clients)

![Configuration of the OAuth Credentials on Google Cloud: https://console.cloud.google.com/auth/clients](/static/img/articles/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise/05.webp)

Configuration of the OAuth Credentials on Google Cloud: [https://console.cloud.google.com/auth/clients](https://console.cloud.google.com/auth/clients)

Crucially, we need to define the “Authorized redirect URIs”. The `localhost` URI is used during local development with the ADK Web UI, and the `https://vertexaisearch.cloud.google.com/oauth-redirect` URI is used by the Vertex AI Agent Engine in production to securely handle the callback after the user grants consent.

### Implementation in ADK

ADK simplifies the OAuth flow significantly. We define the authentication configuration and use decorators to protect the tools that require user credentials.

Here is a snippet demonstrating the core authentication mechanism in the agent code:

```python
"""Authentication for the tools."""

# %% IMPORTS

from fastapi.openapi.models import OAuth2, OAuthFlowAuthorizationCode, OAuthFlows
from google.adk.auth.auth_credential import AuthCredential, AuthCredentialTypes, OAuth2Auth
from google.adk.auth.auth_tool import AuthConfig

from slides_translator_agent import configs

# %% CONFIGS

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = {
    "https://www.googleapis.com/auth/drive": "Google Drive API",
    "https://www.googleapis.com/auth/presentations": "Google Slides API",
}

# %% AUTHENTICATIONS

AUTH_SCHEME = OAuth2(
    flows=OAuthFlows(
        authorizationCode=OAuthFlowAuthorizationCode(
            authorizationUrl=AUTHORIZATION_URL,
            tokenUrl=TOKEN_URL,
            scopes=SCOPES,
        )
    )
)
AUTH_CREDENTIAL = AuthCredential(
    auth_type=AuthCredentialTypes.OAUTH2,
    oauth2=OAuth2Auth(
        client_id=configs.AUTHENTICATION_CLIENT_ID,
        client_secret=configs.AUTHENTICATION_CLIENT_SECRET,
    ),
)
AUTH_CONFIG = AuthConfig(
    auth_scheme=AUTH_SCHEME,
    raw_auth_credential=AUTH_CREDENTIAL,
)
```

When the `translate_presentation` tool is invoked, the `negotiate_creds` function ensures that a valid token exists. If not, ADK automatically pauses the agent execution and initiates the OAuth flow with the user.

```python
"""Tools for the agents."""

import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from slides_translator_agent import auths

def negotiate_creds(tool_context: ToolContext) -> Credentials | dict:
    """Handle the OAuth 2.0 flow to get valid credentials."""
    logger.info("Negotiating credentials using oauth 2.0")
    # Check for cached credentials in the tool state
    if cached_token := tool_context.state.get(configs.TOKEN_CACHE_KEY):
        logger.debug("Found cached token in tool context state")
        if isinstance(cached_token, dict):
            logger.debug("Cached token is a dictionary, treating as AuthCredential.")
            try:
                creds = Credentials.from_authorized_user_info(
                    cached_token, list(auths.SCOPES.keys())
                )
                if creds.valid:
                    logger.debug("Cached credentials are valid, returning credentials")
                    return creds
                if creds.expired and creds.refresh_token:
                    logger.debug("Cached credentials expired, attempting refresh")
                    creds.refresh(Request())
                    tool_context.state[configs.TOKEN_CACHE_KEY] = json.loads(creds.to_json())
                    logger.debug("Credentials refreshed and cached successfully")
                    return creds
            except Exception as error:
                logger.error(f"Error loading/refreshing cached credentials: {error}")
                tool_context.state[configs.TOKEN_CACHE_KEY] = None  # reset cache
        elif isinstance(cached_token, str):
            logger.debug("Found raw access token in tool context state.")
            # This creates a temporary credential object from the token
            # Note: This credential will not be refreshed if it expires
            return Credentials(token=cached_token)
        else:
            raise ValueError(
                f"Invalid cached token type. Expected dict or str, got {type(cached_token)}"
            )
    # If no valid cached credentials, check for auth response
    logger.debug("No valid cached token. Checking for auth response")
    if exchanged_creds := tool_context.get_auth_response(auths.AUTH_CONFIG):
        logger.debug("Received auth response, creating credentials")
        auth_scheme = auths.AUTH_CONFIG.auth_scheme
        auth_credential = auths.AUTH_CONFIG.raw_auth_credential
        creds = Credentials(
            token=exchanged_creds.oauth2.access_token,
            refresh_token=exchanged_creds.oauth2.refresh_token,
            token_uri=auth_scheme.flows.authorizationCode.tokenUrl,
            client_id=auth_credential.oauth2.client_id,
            client_secret=auth_credential.oauth2.client_secret,
            scopes=list(auth_scheme.flows.authorizationCode.scopes.keys()),
        )
        tool_context.state[configs.TOKEN_CACHE_KEY] = json.loads(creds.to_json())
        logger.debug("New credentials created and cached successfully")
        return creds
    # If no auth response, initiate auth request
    logger.debug("No credentials available. Requesting user authentication")
    tool_context.request_credential(auths.AUTH_CONFIG)
    logger.info("Awaiting user authentication")
    return {"pending": True, "message": "Awaiting user authentication"}
```

This ensures the user explicitly consents to the agent accessing their files before any action is taken.

![OAuth is supported natively on Google ADK: when needed, ADK will prompt the user to grant more access to the agent tools](/static/img/articles/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise/06.webp)

OAuth is supported natively on Google ADK: when needed, ADK will prompt the user to grant more access to the agent tools

### Deploying with Gemini Enterprise

Once the agent is developed and tested, the next step is deploying it to production.

### Configuring Production Authentication

Before deploying the agent code, we need to register the OAuth configuration with the production environment. I used the following script to set this up:

```bash
./as.py create-auth \
  --auth-id slides-translator-auth \
  --client-id ... \
  --client-secret ... \
  --auth-uri "https://accounts.google.com/o/oauth2/auth?include_granted_scopes=true&response_type=code&access_type=offline&prompt=consent" \
  --token-uri "https://oauth2.googleapis.com/token" \
  --scope "https://www.googleapis.com/auth/drive" \
  --scope "https://www.googleapis.com/auth/presentations"
```

This command links the `slides-translator-auth` ID (referenced in the Python code above as `configs.TOKEN_CACHE_KEY`) with the actual Client ID, Secret, and the required scopes.

Note: As the Gemini Enterprise exposition API is still in private preview, I can’t share more details nor the deployment script yet.

### Seamless Exposition

[Gemini Enterprise](https://cloud.google.com/gemini/enterprise?authuser=1) gives you a quick way to expose your agent securely and conveniently. This directly addresses the “[UI bottleneck](https://fmind.medium.com/the-real-ai-agent-bottleneck-is-the-damn-ui-90e90ee369e0)” mentioned earlier.

This approach has significant advantages over deploying a separate UI (like Streamlit):

- **Zero-Effort UI:** No need to design, host, or secure a separate frontend application.
- **Observability:** Thanks to the underlying Agent Engine, it traces and logs the agent information automatically, providing essential observability for production monitoring and debugging.
- **Core Services:** It provides more core services and integrates seamlessly within the Google Cloud security perimeter.

The end result is a clean, integrated experience. Users can interact with the “Slides Translator Agent” directly within the Gemini interface.

![Slides Translator Agent deployed on Gemini Enterprise](/static/img/articles/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise/07.webp)

Slides Translator Agent deployed on Gemini Enterprise

### Conclusion

This journey from a simple notebook to a production-ready agent was a great experience to see what this stack provides out of the box. The combination of ADK for development, OAuth for security, and Gemini Enterprise for deployment streamlines the entire lifecycle of an enterprise agent, allowing us to deploy quickly without compromising on security or usability.

I’m eager to explore more ways to build agents. While this is a new paradigm that requires upskilling our teammates and adapting our development practices, we already see the potential from the use cases we see. The ability to rapidly deploy secure, specialized tools that act on behalf of users is a significant step forward.

![Human and Agent merging to accomplish their tasks (Source: Gemini App)](/static/img/articles/powering-up-your-agent-in-production-with-adk-oauth-and-gemini-enterprise/08.webp)

Human and Agent merging to accomplish their tasks (Source: Gemini App)
