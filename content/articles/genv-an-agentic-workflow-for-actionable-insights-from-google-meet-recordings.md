+++
title = "GenV: An Agentic Workflow for Actionable Insights from Google Meet Recordings"
description = "Video meetings on platforms like Google Meet are essential for collaboration, but how often do crucial details get lost moments after the call ends?"
date = "2025-04-11"
tags = ["Agent", "Project"]
slug = "genv-an-agentic-workflow-for-actionable-insights-from-google-meet-recordings"
syndicated = "https://medium.com/@fmind/genv-an-agentic-workflow-for-actionable-insights-from-google-meet-recordings-746d465fb827"
draft = false
+++

Video meetings on platforms like [Google Meet](https://www.google.com/search?q=google+meet&rlz=1CAAUGU_enFR1042&oq=google+meet&gs_lcrp=EgZjaHJvbWUyCQgAEEUYORiABDIGCAEQIxgnMgcIAhAAGIAEMgcIAxAAGIAEMgcIBBAAGIAEMgYIBRBFGDwyBggGEEUYPDIGCAcQRRg80gEIMTIxMmowajeoAgCwAgA&sourceid=chrome&ie=UTF-8#:~:text=Google%20Meet%20%2D%20Online,meet.google.com) are essential for collaboration, but how often do crucial details get lost moments after the call ends? Decisions are made, action items are assigned, and valuable context is shared, only to become buried in recordings that are rarely revisited. Manually scrubbing through hours of video to find specific information is tedious and inefficient.

As someone deeply involved in AI, Generative AI, and MLOps, I saw another opportunity to apply these technologies to a common challenge. How can we efficiently extract the key takeaways, action items, and decisions from our meeting recordings without the manual effort?

This led to the creation of [**GenV (Generative AI for Video Analytics)**](https://github.com/fmind/GenV), a [Python notebook](https://github.com/fmind/GenV/blob/main/GenV_Generative_AI_for_Video_Analytics.ipynb) designed as an agent to distill Google Meet recordings into structured, actionable insights. Similar to my previous [BKFC project for Google Chat](https://fmind.medium.com/bkfc-an-agentic-workflow-for-gathering-knowledge-from-google-chat-b521cba535d7), the goal was to build a practical, focused agentic workflow using powerful, accessible tools like [Google Colab](https://colab.google/), [Google Cloud Storage](https://cloud.google.com/storage?authuser=1), the [Vertex AI API](https://cloud.google.com/vertex-ai/docs/start/introduction-unified-platform?authuser=1), and specifically, [Vertex AI’s Gemini models](https://cloud.google.com/vertex-ai/generative-ai/docs/overview?authuser=1).

![GenV: An Agentic Workflow for Actionable Insights from Google Meet Recordings](/static/img/articles/genv-an-agentic-workflow-for-actionable-insights-from-google-meet-recordings/cover.webp)

### The Motivation: From Video Overload to Clear Takeaways

[Google Meet](https://meet.google.com/) recordings often contain a wealth of information:

- Detailed discussions and brainstorming sessions.
- Project updates and status reports.
- Decisions made and rationale explained.
- Action items assigned, sometimes with owners and deadlines.
- Technical details, configurations, or troubleshooting steps discussed.
- Feedback and suggestions shared.

Relying on memory or manual note-taking during meetings is often insufficient. Rewatching recordings is time-consuming, and note taking apps are too generic to capture specific contents and insights. [GenV](https://github.com/fmind/GenV) aims to automate the process of extracting structured knowledge from these video assets.

### How GenV Works: An Agentic Workflow for Video

GenV follows a clear agentic process: **Locate -\> Prepare -\> Analyze -\> Report**.

**Setup & Authentication:** Standard Google Cloud setup is required. This involves enabling the Vertex AI API in your GCP project and potentially creating a GCS bucket. The script uses `google.colab.auth` library for secure access. Google Drive access is also needed to locate the Meet recordings.

**Locate & Prepare Data (Perception & Preparation):** The agent first needs access to the video files.

- It mounts your Google Drive to access the specified path for Meet recordings (e.g., `MyDrive/Meet Recordings`).
- It identifies video files modified within a recent period (e.g., last 30 days, configurable via `SINCE_DAYS`).
- Crucially, because the Vertex AI API often works best with cloud storage, the script uploads these video files from Drive to a designated Google Cloud Storage (GCS) bucket if they don’t already exist there. This prepares the video for analysis.

**Analyze Data (Reasoning & Action):** This is where Vertex AI’s Gemini model performs the heavy lifting.

- **Structured Output Definition:** Like with BKFC, defining the _desired_ output structure is key. We use [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/) to create a detailed schema, `MeetingInsight`, specifying exactly what information to extract. This includes fields for:
- `title`: Inferred meeting title.
- `summary`: A concise meeting summary.
- `questions_answers`: Pairs of questions and answers.
- `unanswered_questions`: Questions lacking clear answers.
- `projects_discussed`: Project updates and details.
- `action_items`: Tasks with potential owners and deadlines.
- `decisions_suggestions`: Key decisions or proposals.
- `technical_insights`: Technical details mentioned.
- `key_topics_mentioned`: Other important themes or keywords.

&nbsp;

```python
class MeetingInsight(pdt.BaseModel):
    """Structured insights extracted from a Google Meet recording analysis."""
    title: T.Optional[str] = pdt.Field(
        default=None,
        description="The inferred title or primary subject of the meeting based on the discussion."
    )
    summary: T.Optional[str] = pdt.Field(
        default=None,
        description="A concise summary (3-5 sentences) of the main topics discussed and key outcomes of the meeting."
    )
    questions_answers: T.Optional[list[QuestionAnswer]] = pdt.Field(
        default=None,
        description="A list of significant questions asked and their corresponding answers from the meeting."
    )
    unanswered_questions: T.Optional[list[str]] = pdt.Field(
        default=None,
        description="A list of significant questions that were asked but do not appear to have been clearly answered during the meeting.."
    )
    projects_discussed: T.Optional[list[ProjectInfo]] = pdt.Field(
        default=None,
        description="A list of specific projects discussed, including status or key points."
    )
    action_items: T.Optional[list[ActionItem]] = pdt.Field(
        default=None,
        description="A list of specific tasks or action items assigned, including owner and deadline if specified."
    )
    decisions_suggestions: T.Optional[list[DecisionSuggestion]] = pdt.Field(
        default=None,
        description="A list of key decisions made or significant suggestions proposed during the meeting."
    )
    technical_insights: T.Optional[list[str]] = pdt.Field(
       default=None,
       description="Specific mentions related technical solutions, configurations, or code snippets discussed."
    )
    key_topics_mentioned: T.Optional[list[str]] = pdt.Field(
        default=None,
        description="A list of other important topics, keywords, or themes discussed that are not captured elsewhere (e.g., specific technologies, methodologies, upcoming events, general announcements)."
    )
```

- **API Call:** For each video file (referenced by its GCS URI), the script sends a request to the [Gemini model](https://cloud.google.com/vertex-ai/generative-ai/docs/models) (`gemini-2.0-flash` or similar multimodal model). The key here is providing the video URI directly to the model, along with the prompt and, importantly, specifying the `response_mime_type` as `application/json` and providing the `response_schema` (our `MeetingInsight` Pydantic model). This multimodal capability combined with structured output is incredibly powerful.
- **Parsing:** The Gemini API directly returns JSON conforming to the schema, which the library automatically parses into our Pydantic `MeetingInsight` object.

&nbsp;

```python
# Simplified Gemini API Call Example
uri = f"gs://{blob.bucket.name}/{blob.name}" # GCS URI of the video
contents = [
    GT.Part.from_uri(file_uri=uri, mime_type="video/mp4"),
    prompt, # Your prompt guiding the analysis
]
response = genai_client.models.generate_content(
    model=MODEL, # e.g., "gemini-2.0-flash"
    contents=contents,
    config={
        "response_mime_type": "application/json",
        "response_schema": MeetingInsight, # Providing the schema
        "temperature": TEMPERATURE
    },
)
insight = response.parsed # The structured Pydantic object
```

**Report Results (Output):** The final step presents the insights clearly.

- The script iterates through the `MeetingInsight` objects for each video.
- It generates readable Markdown summaries, organizing the extracted information under relevant headings (Summary, Q&A, Projects, Action Items, Decisions, etc.). See example below.
- It also saves the raw structured data to a `jsonlines` file for potential downstream use.

_**Example Output Snippet (from**_ _**`video_insights.txt`**):_**

```markdown
# MLOps Community - Kubeflow

## Meeting Title

Kubeflow: The ML Toolkit for Kubernetes

## Summary

The speaker introduces Kubeflow as a toolkit for doing machine learning on top of Kubernetes. He outlines the agenda for the presentation, which includes components, architecture, ML workflow, Kubeflow pipelines, and a Q&A session. He emphasizes that Kubeflow is an open-source ML Ops platform based on Kubernetes, primarily using Python and YAML.

## Projects Discussed

- **Kubeflow:** Kubeflow is an open-source ML Ops platform based on Kubernetes, primarily using Python and YAML. It is a tool to power the develop platform with Kubernetes. The project has been sponsored by Google.

## Technical Insights

- Kubeflow uses Python and YAML.
- Kubeflow is based on Kubernetes.
- Kubeflow uses Docker.

## Key Topics

- MLOps
- Kubernetes
- Python
- YAML
- Docker
- Pipelines
- Components
- Architecture
```

### The Value Proposition: Why Use GenV?

This focused agent provides tangible benefits:

- **Rapid Meeting Summarization:** Get the gist and key outcomes of meetings quickly without rewatching.
- **Action Item Extraction:** Reliably capture tasks, owners, and deadlines mentioned during calls.
- **Decision Tracking:** Easily reference key decisions made and suggestions proposed.
- **Knowledge Retrieval:** Quickly find specific technical details, project updates, or answers discussed.
- **Identify Follow-ups:** Surface unanswered questions needing attention.
- **Efficiency Boost:** Saves significant time compared to manual review or note-taking.
- **Practical AI Demonstration:** Showcases how multimodal models like Gemini combined with structured output can automate information extraction from video content.

### Conclusion: Tapping into Video Knowledge with Focused AI

The [GenV notebook](https://github.com/fmind/GenV/blob/main/GenV_Generative_AI_for_Video_Analytics.ipynb) demonstrates how agentic workflows powered by multimodal AI can unlock the valuable information trapped within video recordings. By leveraging the analytical power of [Vertex AI’s Gemini models](https://cloud.google.com/vertex-ai/generative-ai/docs/models), guided by precise structured output schemas, we can transform hours of meeting video into concise, actionable summaries.

This highlights that sophisticated AI benefits don’t always require complex conversational agents. Focused, task-specific agents like [GenV](https://github.com/fmind/GenV) can automate laborious processes and make information more accessible. For those of us working in AI and MLOps, building such targeted solutions using cloud platforms like Google Cloud is increasingly feasible, allowing us to enhance productivity and knowledge sharing.

What other types of content could benefit from automated, structured insight extraction using Generative AI? Let me know your thoughts!

![GenV: An Agentic Workflow for Actionable Insights from Google Meet Recordings](/static/img/articles/genv-an-agentic-workflow-for-actionable-insights-from-google-meet-recordings/02.webp)
