+++
title = "Forging a Personal Chatbot with OpenAI API, Chroma DB, HuggingFace Spaces, and Gradio 🔥"
description = "If you have checked the Internet in 2023, you’re likely familiar with Generative AI."
date = "2023-10-24"
tags = ["LLM", "RAG", "Demo"]
slug = "forging-a-personal-chatbot-with-openai-api-chroma-db-huggingface-spaces-and-gradio"
syndicated = "https://medium.com/@fmind/forging-a-personal-chatbot-with-openai-api-chroma-db-huggingface-spaces-and-gradio-bc50e7a93071"
draft = false
+++

[If you have checked the Internet in 2023](https://www.zdnet.com/article/generative-ai-is-everything-everywhere-all-at-once/), you’re likely familiar with [Generative AI](https://en.wikipedia.org/wiki/Generative_artificial_intelligence). The [launch of ChatGPT](https://openai.com/blog/chatgpt) has sparked a surge in [interest](https://github.com/f/awesome-chatgpt-prompts), [investment](https://fortune.com/2023/08/30/chatgpt-creator-openai-earnings-80-million-a-month-1-billion-annual-revenue-540-million-loss-sam-altman/), and [innovative projects](https://autogpt.net/) focused on [Large Language Models](https://en.wikipedia.org/wiki/Large_language_model) (LLMs), [Artificial General Intelligence](https://en.wikipedia.org/wiki/Artificial_general_intelligence) (AGI), and [Retrieval Augmented Generation](https://www.promptingguide.ai/techniques/rag) (RAG). Yet, [navigating this burgeoning field can be challenging](https://web.archive.org/web/20230616022719/https://mlops.community/surveys/llm/): What tangible benefits does Generative AI offer? How complex is it to develop a Generative AI application? What kind of performance can one expect from such applications in real-world projects?

**In this article, I outline a project I developed to field questions about my resume and deepen my understanding of Generative AI**. The first section introduces the use case, objectives, and tools chosen for the project. The second section details the steps involved in converting unstructured documents into Chroma DB, a vector database. The third section elaborates on how to construct and integrate a chatbot assistant utilizing the OpenAI API, HuggingFace Spaces, and Gradio. Finally, I delve into the merits of learning through practical experience, along with critical design choices — such as the deliberate decision not to employ LangChain for this project.

![Forging a Personal Chatbot with OpenAI API, Chroma DB, HuggingFace Spaces, and Gradio 🔥](/static/img/articles/forging-a-personal-chatbot-with-openai-api-chroma-db-huggingface-spaces-and-gradio/cover.webp)

### A Case for a Chatbot 💼

#### What? 💬

- **Develop a chatbot capable of answering questions related to my** [**LinkedIn profile**](https://www.linkedin.com/in/fmind-dev/) **.**
- Process unstructured documents and rank them based on user queries.
- Deploy the chatbot online and integrate it into [my website](https://www.fmind.dev/).

#### Why? 📡

- **Acquire hands-on experience with new technology via a tangible project.**
- Engage recruiters through more naturalized interactions.
- Evaluate the readiness of Generative AI tooling.

#### How? 🛠️

- **Large Language Model (LLM)**: [gpt-3.5-turbo-16k](https://platform.openai.com/docs/models) ([OpenAI](https://openai.com/))
- **Embedding Model**: [text-embedding-ada-002](https://platform.openai.com/docs/guides/embeddings) ([OpenAI](https://openai.com/))
- **Encoding Model**: cl100k_base ([tiktoken](https://github.com/openai/tiktoken))
- **Vector Database**: [Chroma DB](https://www.trychroma.com/)

**Note**: [LangChain](https://www.langchain.com/) was deliberately not utilized (discussed later).

### From Data to Vector Database ↗️

#### Downloading my LinkedIn Page 🌐

Websites are keen to protect their assets, even when those assets are your personal information. To furnish my chatbot with sufficient data, I manually downloaded [my public LinkedIn profile](https://www.linkedin.com/in/fmind-dev/) and saved it as an HTML file.

While automation could have been employed, I chose not to, in order to sidestep CAPTCHA challenges and other potential restrictions. This decision aligns well with the 80–20 rule, whereby 80% of the desired outcomes are achieved with just 20% of the effort.

![My public profile on LinkedIn: https://www.linkedin.com/in/fmind-dev/](/static/img/articles/forging-a-personal-chatbot-with-openai-api-chroma-db-huggingface-spaces-and-gradio/02.webp)

My public profile on LinkedIn: [https://www.linkedin.com/in/fmind-dev/](https://www.linkedin.com/in/fmind-dev/)

#### Converting HTML to Markdown 📑

HTML is a well-structured yet verbose and cluttered format, rife with attributes and styles. To streamline the content, I first converted the HTML file into a plain text file using [Pandoc](https://pandoc.org/). Subsequently, I manually transformed this text file into Markdown to enhance both its format and content.

```bash
pandoc --to=plain --from=html --output=files/linkedin.txt files/linkedin.html
```

**Through my experimentation, I’ve found that data quality is pivotal in optimizing the performance of a language model**. Given the limited control one has over the flow of an LLM, ensuring that the data is correctly formatted and relevant significantly aids in validating the model’s behavior.

```markdown
# Profile

## Overview

- First name: Médéric
- Last name: HURIER
- Pseudo: Fmind
- Followers: 4K
- Location: Luxembourg, Luxembourg
- Education: University of Luxembourg
- Current position: Decathlon Technology
- Public URL: www.linkedin.com/in/fmind-dev
- Industry: Technology, Information and Internet
- Address: 28 Avenue François Clément, 5612 Mondorf-les-Bains, Luxembourg
- Headline: Freelancer | AI/ML/MLOps Engineer | Data Scientist | MLOps Community Organizer | OpenClassrooms Mentor | Hacker | PhD
```

#### Chunking and Importing Data to Chroma DB 🛢

**One of the primary constraints of Large Language Models is their context size**. As of October 2023, OpenAI’s [GPT-3.5 models](https://developers.openai.com/api/docs/models) support context sizes ranging from 4k to 16k tokens, while [GPT-4 models](https://platform.openai.com/docs/models/gpt-4) extend this range from 8k to 32k tokens. **In my evaluation, the cost-to-benefit ratio was more favorable for GPT-3.5 than for GPT-4.**

```markdown
| Technical name    | Model family | Price per 1000 tokens   | Max tokens |
| ----------------- | ------------ | ----------------------- | ---------- |
| gpt-4-32k         | GPT-4        | USD 0.0600 (prompt)     | 32768      |
|                   |              | USD 0.1200 (completion) |            |
| gpt-4             | GPT-4        | USD 0.0300 (prompt)     | 8192       |
|                   |              | USD 0.0600 (completion) |            |
| gpt-3.5-turbo-16k | GPT-3.5      | USD 0.0030 (prompt)     | 16384      |
|                   |              | USD 0.0040 (completion) |            |
| gpt-3.5-turbo     | GPT-3.5      | USD 0.0015 (prompt)     | 4096       |
|                   |              | USD 0.0020 (completion) |            |
```

To divide my Markdown document into manageable chunks, I developed a Python function that segments content based on header levels, easily achieved through regular expressions:

```python
def segment_text(text: str, pattern: str) -> T.Iterator[tuple[str, str]]:
    """Segment the text in title and content pair by pattern."""
    splits = re.split(pattern, text, flags=re.MULTILINE)
    pairs = zip(splits[1::2], splits[2::2])
    return pairs

segments_h1 = segment_text(text=text, pattern=r"^# (.+)")
segments_h2 = segment_text(text=h1_text, pattern=r"^## (.+)")
```

Subsequently, I crafted another function to import these chunks into Chroma DB. [**Chroma DB**](https://www.trychroma.com/) **is particularly useful for straightforward applications, given its in-memory operation and simplicity**. The following code snippet outlines how to prepare the document, metadata, and identifiers for ingestion into a collection:

```python
def import_file(
    file: T.TextIO,
    collection: lib.Collection,
    encoding_function: T.Callable,
    max_output_tokens: int = lib.ENCODING_OUTPUT_LIMIT,
):
    """Import a markdown file to a database collection."""
    text = file.read()
    filename = file.name
    segments_h1 = segment_text(text=text, pattern=r"^# (.+)")
    for h1, h1_text in segments_h1:
        segments_h2 = segment_text(text=h1_text, pattern=r"^## (.+)")
        for h2, content in segments_h2:
            id_ = f"{filename} # {h1} ## {h2}"  # unique doc id
            document = f"# {h1}\n\n## {h2}\n\n{content.strip()}"
            metadata = {"filename": filename, "h1": h1, "h2": h2}
            collection.add(ids=id_, documents=document, metadatas=metadata)
```

### Building, Hosting, and Integrating a Chatbot 👨‍💻

#### Chatbot Function 🤖

The chatbot function serves as the system’s core. It is responsible for crafting responses based on the conversation history, the user’s input, and the context prompt. Additionally, the function can fetch pertinent information from the Vector Database to enrich the content (via RAG). **It’s crucial at this stage to not exceed the token limitations imposed by the LLM and to refrain from including irrelevant information for the end user (i.e., by filtering documents by their distance).**

Once the responses are formulated, they are sent to the Large Language Model for processing. **In my case, I utilized** [**OpenAI’s GPT-3.5 16k model**](https://developers.openai.com/api/docs/models) **, as it offered the most favorable balance among model performance, context size, and cost per token**. The model’s output can then be displayed directly to the user:

```python
PROMPT_CONTEXT = """
You are Fmind Chatbot, specialized in providing information regarding Médéric Hurier's (known as Fmind) professional background.
Médéric is an MLOps engineer based in Luxembourg. He is currently working at Decathlon. His calendar is booked until the conclusion of 2024.
Your responses should be succinct and maintain a professional tone. If inquiries deviate from Médéric's professional sphere, courteously decline to engage.

You may find more information about Médéric below (markdown format):
"""

def answer(message: str, history: list[str]) -> str:
    """Answer questions about my resume."""
    # counters
    n_tokens = 0
    # messages
    messages = []
    # - context
    n_tokens += len(ENCODING(PROMPT_CONTEXT))
    messages += [{"role": "system", "content": PROMPT_CONTEXT}]
    # - history
    for user_content, assistant_content in history:
        n_tokens += len(ENCODING(user_content))
        n_tokens += len(ENCODING(assistant_content))
        messages += [{"role": "user", "content": user_content}]
        messages += [{"role": "assistant", "content": assistant_content}]
    # - message
    n_tokens += len(ENCODING(message))
    messages += [{"role": "user", "content": message}]
    # database
    results = COLLECTION.query(query_texts=message, n_results=QUERY_N_RESULTS)
    distances, documents = results["distances"][0], results["documents"][0]
    for distance, document in zip(distances, documents):
        # - distance
        if distance > QUERY_MAX_DISTANCE:
            break
        # - document
        n_document_tokens = len(ENCODING(document))
        if (n_tokens + n_document_tokens) >= PROMPT_MAX_TOKENS:
            break
        n_tokens += n_document_tokens
        messages[0]["content"] += document
    # response
    api_response = MODEL(messages=messages)
    content = api_response["choices"][0]["message"]["content"]
    # return
    return content
```

#### Chatbot Interface: Gradio 🖼️

Multiple avenues are available for constructing a chat interface, ranging from developing a full-fledged web application (e.g., using [Flask](https://flask.palletsprojects.com/en/3.0.x/)) to rapidly prototyping via [Streamlit](https://streamlit.io/) or [Dash](https://plotly.com/dash/). **In my scenario, I opted for** [**Gradio**](https://www.gradio.app/) **because it provides a prebuilt chat interface.**

Despite its simplicity, [Gradio](https://www.gradio.app/) offers ample room for customization. I was able to fine-tune the interface by eliminating extraneous buttons, selecting an appropriate theme, and showcasing example interactions to the end user.

```python
interface = gr.ChatInterface(
    fn=answer,
    theme=THEME,
    title="glass",
    examples=EXAMPLES,
    clear_btn=None,
    retry_btn=None,
    undo_btn=None,
)
```

#### Chatbot Hosting: HuggingFace Spaces 🗄️

**Choosing the right hosting option proved to be the most challenging decision**. While cloud providers like [AWS](https://aws.amazon.com/), [GCP](https://cloud.google.com/), and [Azure](https://azure.microsoft.com/en-us) offer scalable solutions, they come with a complex setup process involving permissions and public access. Conversely, I found [HuggingFace Spaces](https://huggingface.co/spaces) to be user-friendly, cost-effective, and natively supportive of Gradio. **Given that personal websites typically don’t demand high scalability, I opted for HuggingFace Spaces.**

![Hosting on HuggingFace Spaces: https://huggingface.co/spaces/fmind/resume](/static/img/articles/forging-a-personal-chatbot-with-openai-api-chroma-db-huggingface-spaces-and-gradio/03.webp)

Hosting on HuggingFace Spaces: [https://huggingface.co/spaces/fmind/resume](https://huggingface.co/spaces/fmind/resume)

#### Chatbot Integration: Embed with a Web Component 📲

The final stage involved integrating the chatbot into my website. This task was exceptionally straightforward, as [HuggingFace Spaces](https://huggingface.co/spaces) allows for the creation of a web component — an HTML snippet that can be seamlessly added to any site.

```html
<script
 type="module"
 src="https://gradio.s3-us-west-2.amazonaws.com/3.46.0/gradio.js"
></script>

<gradio-app src="https://fmind-resume.hf.space"></gradio-app>
```

And there you have it! [A personal chatbot is now integrated into my website, ready to field your questions](https://www.fmind.dev/).

![AI Chatbot integrated into my website: https://www.fmind.dev/](/static/img/articles/forging-a-personal-chatbot-with-openai-api-chroma-db-huggingface-spaces-and-gradio/04.webp)

AI Chatbot integrated into my website: [https://www.fmind.dev/](https://www.fmind.dev/)

### Conclusions 🏁

#### Learning by Doing ✍

**Creating a personal AI assistant based on my LinkedIn profile was a deeply enriching experience**. It provided me an opportunity to explore new tools and APIs like Chroma DB, while revisiting familiar ones like OpenAI and Gradio. Moreover, I confronted challenges specific to RAG applications, including proper content chunking, data quality improvement, and the seamless integration of multiple tools into a comprehensive solution.

#### To Use LangChain or Not? ⛓

[The utility of LangChain is a subject of debate within the community](https://minimaxir.com/2023/07/langchain-problem/). Although the framework offers several conveniences for managing LLMs, I found its practical application cumbersome. I spent more time navigating its documentation and grappling with its components than actually building my own. In my view, the abstractions it provides can be unduly complex relative to what can be accomplished more directly.

#### To Infinity and Beyond with Gen AI! 💫

**The process of crafting a personal AI assistant was engaging, and educational**. My next steps involve fine-tuning a model and comparing its performance against a standard RAG application, [a topic also discussed within the MLOps Community](https://mlops-community.slack.com/archives/C04T55KFV8S/p1697887950188599). Now, more than ever, I recognize the transformative potential of Generative AI in both existing and emerging solutions. May we realize the full potential of Generative AI in our lifetime!

![DALL-E 3: Draw a picture of a bright future with Artificial Intelligence. I want something inspiring for a blog post on Medium.](/static/img/articles/forging-a-personal-chatbot-with-openai-api-chroma-db-huggingface-spaces-and-gradio/05.webp)

DALL-E 3: Draw a picture of a bright future with Artificial Intelligence. I want something inspiring for a blog post on Medium.
