+++
title = "BKFC: An Agentic Workflow for Gathering Knowledge from Google Chat"
description = "Team collaboration often lives and breathes within chat applications like Google Chat or Slack."
date = "2025-04-08"
tags = ["Agent", "Project"]
slug = "bkfc-an-agentic-workflow-for-gathering-knowledge-from-google-chat"
syndicated = "https://medium.com/@fmind/bkfc-an-agentic-workflow-for-gathering-knowledge-from-google-chat-b521cba535d7"
draft = false
+++

### BKFC: **An Agentic Workflow for** Gathering **Knowledge from Google Chat**

Team collaboration often lives and breathes within chat applications like [Google Chat](https://chat.google.com/) or [Slack](https://slack.com/). It’s where questions are asked, decisions are made, project updates are shared, and solutions are brainstormed. But let’s be honest: extracting specific information from weeks or months of chat history can feel like searching for a needle in a haystack. Important context gets buried, action items are forgotten, and valuable knowledge becomes siloed.

As someone passionate about AI, Generative AI, and MLOps, I’m always looking for practical ways to leverage these technologies to solve real-world problems. The challenge of unlocking the latent knowledge within Google Chat seemed like a perfect opportunity. How could we quickly surface key insights without manual scrolling and searching?

This led me to create [**BKFC (Build Knowledge From Chats)**](https://github.com/fmind/BKFC), a [Python notebook](https://github.com/fmind/BKFC/blob/main/BKFC_Build_a_Knowledge_base_From_Chats.ipynb) designed to act as a simple yet powerful insight-gathering agent for Google Chat. My goal wasn’t just to extract information, but also to demonstrate how quickly valuable, focused agentic workflows can be built using modern tools like [Google Colab](https://colab.google/), the [Google Chat API](https://developers.google.com/workspace/chat), and [Vertex AI’s Gemini models](https://cloud.google.com/vertex-ai/generative-ai/docs/overview).

![BKFC: An Agentic Workflow for Gathering Knowledge from Google Chat](/static/img/articles/bkfc-an-agentic-workflow-for-gathering-knowledge-from-google-chat/cover.webp)

### The Motivation: From Chat Chaos to Actionable Insights

In many teams, Google Chat spaces become informal knowledge repositories. You might find:

- Questions asked and answered.
- Updates on ongoing projects.
- Implicit or explicit action items.
- Valuable technical discussions, code snippets, or configuration details.
- Feedback and suggestions for improvement.

**Manually scrolling through this history is inefficient and error-prone**. Key information can be easily missed, especially as teams grow and conversations multiply. I wanted a way to automatically distill recent conversations into structured, actionable summaries.

### How BKFC Works: An Agentic Workflow in Action

The notebook follows a straightforward, agentic process: **Fetch -\> Process -\> Analyze -\> Report**.

**Setup & Authentication:** The first step involves standard Google Cloud setup. This means enabling the Google Chat and Vertex AI APIs in a GCP project and creating OAuth credentials (specifically for a Desktop app) to allow the script to securely access chat data on your behalf. Colab’s secrets management handles the client ID, secret, and project ID securely. Authentication uses the `gcloud auth application-default login` flow, granting the necessary `chat.spaces.readonly` and `chat.messages.readonly` scopes.

```bash
!gcloud auth application-default login --no-browser --client-id-file={SECRETS} --scopes={",".join(SCOPES)}
```

**Fetch Data (Perception):** The agent’s “perception” phase involves using the `googleapiclient` library to interact with the Google Chat API.

- It lists all chat spaces the authenticated user has access to.
- It filters these spaces to only include those active within a defined recent period (e.g., the last 100 days, configurable via `SINCE_DAYS`).
- For each relevant space, it fetches messages created since that period, respecting API pagination (`PAGE_SIZE`).

&nbsp;

```python
spaces = []
page_token = None
while True:
    response = chat_service.spaces().list(pageSize=PAGE_SIZE, pageToken=page_token).execute()
    for space in response.get('spaces', []):
        last_active_time = dt.datetime.fromisoformat(space['lastActiveTime'])
        last_active_date = last_active_time.date()
        if last_active_date >= since:
            spaces.append(space)
    if not page_token:
        break
len(spaces)
```

**Process Data (Preparation):** The raw message data needs some structuring before analysis.

- Messages are sorted chronologically within their respective spaces and threads.
- They are then grouped by the parent chat space.
- For each space, the formatted text of the messages is concatenated into a single “page” or document representing the recent conversation history for that space.

&nbsp;

```python
messages = []
for space in spaces:
    page_token = None
    while True:
        response = chat_service.spaces().messages().list(
            parent=space['name'],
            filter=f'createTime > "{since}T00:00:00+00:00"',
            orderBy='createTime DESC',
            pageToken=page_token,
            pageSize=PAGE_SIZE,

        ).execute()
        messages.extend(response.get('messages', []))
        if not page_token:
            break
len(messages)
...
messages = sorted(messages, key=message_sorted_key, reverse=True)
groups = {key: list(values) for key, values in it.groupby(messages, key=message_groupby_key)}
```

**Analyze Data (Reasoning & Action):** This is where the Gen AI magic happens, powered by Gemini via the Vertex AI API (`python-genai` library).

- **Structured Output Definition:** A key aspect is defining _what_ we want to extract. I used [Pydantic](https://docs.pydantic.dev/latest/) models to define a clear schema (`ChatInsight`) for the desired output. This schema includes fields for:
- `summary`: A concise overview of the discussion.
- `questions_answers`: Pairs of questions and their corresponding answers found in the chat.
- `unanswered_questions`: Questions asked that appear unresolved.
- `projects`: Mentioned projects and their status/details.
- `action_items`: Tasks identified, potentially with assignees.
- `feedback_suggestions`: Ideas or critiques shared.
- `technical_insights`: Specific mentions of MLOps, AI tools (like Vertex AI), code, etc.

&nbsp;

```python
# --- Define the main structure for the overall chat insights ---
class ChatInsight(pdt.BaseModel):
  """Structured insight extracted from a Google Chat conversation history."""
  summary: T.Optional[str] = pdt.Field(...)
  questions_answers: T.Optional[list[QuestionAnswerPair]] = pdt.Field(...)
  unanswered_questions: T.Optional[list[str]] = pdt.Field(...)
  projects: T.Optional[list[ProjectInfo]] = pdt.Field(...)
  action_items: T.Optional[list[ActionItem]] = pdt.Field(...)
  feedback_suggestions: T.Optional[list[str]] = pdt.Field(...)
  technical_insights: T.Optional[list[str]] = pdt.Field(...)
  # (Inner classes like QuestionAnswerPair, ProjectInfo defined elsewhere)
```

- **API Call:** For each space’s conversation page, a prompt is sent to the Gemini model (`gemini-2.0-flash` is a great choice for speed and cost-effectiveness here). Crucially, the API call specifies the desired `response_mime_type` as `application/json` and provides the `response_schema` (our `ChatInsight` Pydantic model). This instructs Gemini to format its response according to our defined structure.
- **Parsing:** The library automatically parses the JSON response back into a Pydantic `ChatInsight` object.

&nbsp;

```python
insights = {}
for key, page in pages.items():
    page = pages[key]
    prompt = ANALYSIS_TEMPLATE.substitute(page=page)
    try:
        response = genai_client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": ChatInsight,
                "temperature": TEMPERATURE
            },
        )
        print(key, response.usage_metadata.total_token_count)
        insights[key] = response.parsed
    except Exception as error:
        print(f"An error occurred during API call for space {key}: {error}")
len(insights)
```

**Report Results (Output):** The final step is presenting the extracted insights.

- The structured `ChatInsight` objects are iterated through.
- Readable Markdown summaries are generated for each chat space, organizing the extracted information under clear headings (Summary, Q&A, Projects, Actions, etc.).
- The raw structured data is also saved to a `jsonlines` file, which is ideal for potential downstream processing or integration with other tools.

&nbsp;

```markdown
## Summary

Discussions highlight active development of AI solutions, particularly using LLMs for document analysis and market prediction. A strong emphasis emerged on the necessity of solid **MLOps** practices for managing these initiatives effectively, including standardization and deployment strategies, even as significant budgets are approved.

## Projects

- **Predictive Insights Initiative:** Focuses on leveraging LLMs for market trends, with explicit discussion around needing standardized MLOps pipelines for deployment and monitoring.

## Feedback & Suggestions

- Suggestion to establish shared MLOps best practices across teams working on similar ML problems to improve efficiency and consistency.

## Technical Insights

- Need identified for standardized ML model deployment and monitoring pipelines.
- Importance of data standardization for reliable LLM inputs emphasized.
```

### The Value Proposition: Why Bother?

This simple notebook, acting as a focused agent, delivers this added value:

- **Rapid Knowledge Retrieval:** Quickly get summaries and key points from recent chats without manual searching.
- **Action Item Tracking:** Surface potential tasks or commitments that might have been missed.
- **Project Awareness:** Get a quick pulse check on mentioned projects.
- **Identify Unanswered Questions:** Highlight areas where follow-up might be needed.
- **Technical Knowledge Sharing:** Easily find references to specific tools, techniques, or solutions discussed.
- **Efficiency:** Saves considerable time compared to manual review.
- **Demonstrates Practical AI:** Shows how easily accessible Gen AI models and APIs can be combined to build genuinely useful tools _today_.

### Conclusion: Simple Agents, Tangible Value

The [BKFC notebook](https://github.com/fmind/BKFC/blob/main/BKFC_Build_a_Knowledge_base_From_Chats.ipynb) is a practical example of how agentic workflows, even simple ones, can provide immediate value. By combining the power of the Google Chat API to access data and the reasoning capabilities of Gemini models guided by structured schemas, we can transform conversational noise into actionable insights.

It highlights that you don’t always need complex, multi-turn conversational agents to benefit from AI. Focused, task-specific agents like this can automate tedious processes and unlock information trapped in our daily communication streams. As AI and MLOps practitioners, building these kinds of targeted solutions is becoming increasingly straightforward, enabling us to enhance productivity and knowledge sharing within our teams.

What other routine information retrieval tasks could be automated with a similar approach? Let me know in comments!

- **Github Repository**: [https://github.com/fmind/BKFC](https://github.com/fmind/BKFC)
- **Colab Notebook**: [https://github.com/fmind/BKFC](https://github.com/fmind/BKFC) [https://github.com/fmind/BKFC/blob/main/BKFC_Build_a_Knowledge_base_From_Chats.ipynb](https://github.com/fmind/BKFC/blob/main/BKFC_Build_a_Knowledge_base_From_Chats.ipynb)

![BKFC: An Agentic Workflow for Gathering Knowledge from Google Chat](/static/img/articles/bkfc-an-agentic-workflow-for-gathering-knowledge-from-google-chat/02.webp)
