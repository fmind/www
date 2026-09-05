+++
title = "Fixing the MLOps Survey on LLMs with ChatGPT API: Lessons Learned"
description = "Large Language Model (LLM) is such an exciting topic. Since the release of ChatGPT, we saw a surge of innovation ranging from education…"
date = "2023-05-08"
tags = ["LLM", "MLOps", "Demo"]
slug = "fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned"
syndicated = "https://medium.com/@fmind/fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned-62d90e721331"
draft = false
+++

[Large Language Model](https://en.wikipedia.org/wiki/Large_language_model) (LLM) is such an exciting topic. Since [the release of ChatGPT](https://openai.com/blog/chatgpt), we saw [a surge of innovation](https://www.entrepreneur.com/leadership/how-to-use-chatgpt-to-unlock-new-levels-of-innovation/446151) ranging from [education mentorship](https://techcrunch.com/2023/05/05/openai-chatgpt-chegg-edtech/) to [finance advisory](https://www.bloomberg.com/company/press/bloomberggpt-50-billion-parameter-llm-tuned-finance/). Each week is a new opportunity for [addressing new kinds of problems](https://blog.character.ai/introducing-character/), [increasing human productivity](https://www.jasper.ai/), or [improving existing solutions](https://gamerant.com/skyrim-mod-ai-npc-memories/). Yet, we may wonder if this is just a new [hype cycle](https://www.gartner.com/en/research/methodologies/gartner-hype-cycle) or if [organizations are truly adopting LLMs at scale](https://www.forbes.com/sites/forbestechcouncil/2023/04/25/the-generative-ai-frontier-mastering-llm-adoption-for-ceos-and-ctos-to-drive-business-success/) …

![Photo by Brett Jordan on Unsplash](/static/img/articles/fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned/cover.webp)

Photo by [Brett Jordan](https://unsplash.com/@brett_jordan?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

On March 2023, the [MLOps Community](https://mlops.community/) issued [a survey about LLMs in production](https://docs.google.com/forms/d/e/1FAIpQLSerEryK4xHEZTq0hSu-sVmBHilOzaT71BfCQgXe_uIRgIah-g/viewform) to picture the state of adoption. [The survey is full of interesting insights](https://podcasters.spotify.com/pod/show/mlops/episodes/EXCLUSIVE-EPISODE--LLM-Key-Results-e229lbi), but there is a catch: **80% of the questions are** [**open-ended**](https://en.wikipedia.org/wiki/Open-ended_question) **, which means respondents answered the survey freely from a few keywords to full sentences**. I volunteered to clean up the answers with the help of ChatGPT and let the community get a grasp of the survey experiences.

In this article, I present the steps and lessons learned from my journey to shed some light on the MLOps survey on LLMs. I’m first going to present the goal and questions of the survey. Then, I will explain how I used ChatGPT to review the data and standardize the content. Finally, I’m going to evaluate the performance of ChatGPT compared to a manual review.

### Getting to know the MLOps Survey on LLMs

[The MLOps Community’s survey](https://forms.gle/vecVUmAeAyd1m75J6) is composed of 17 questions about the use cases, tools, and concerns for adopting LLMs in production. 110 people replied anonymously to the survey, and the responses can [be accessed at this address](https://docs.google.com/spreadsheets/d/13wdBwkX8vZrYKuvF4h2egPh0LYSn2GQSwUaLV4GUNaU/edit#gid=501618501). The questions asked of the participants are listed below:

> 0\. What is your position/title at your company?

> 1\. How big is your organization? (number of employees)

> 2\. Are you using LLM at in your organization?

> 3\. What is your use case/use cases?

> 4\. Have you integrated or built any internal tools to support LLMs in your org? If so what?

> 5\. What are some of the main challenges you have encountered thus far when building with LLMs?

> 6\. What are your main concerns with using LLMs in production?

> 7\. How are you using LLMs?

> 8\. What tools are you using with LLMs?

> 9\. What areas are you most interested in learning more about?

> 10\. How do you deal with reliability of output?

> 11\. Any stories you have that are worth sharing about working with LLMs?

> 12\. Any questions you have for the community about LLM in production?

> 13\. What is the main reason for not using LLMs in your org?

> 14\. What are some key questions you face when it comes to using LLM in prod?

> 15\. Have you tried LLMs for different use cases in your org?

> 16\. If yes, why did it not work out?

**Except for questions 1, 2, and 7, participants were free to provide any text they wanted for the rest of the questions**. Thus, we can find answers such as “Entity matching, customer service responses (souped up/targetted FAQ)” to Q3 (cell H71) or “Thta it will hallucinate something that we won;t pick up in the report editing phase” to Q6 (I67).

These answers are rich in information, but they are also tricky to analyze: How can we extract the relevant keywords? Can we summarize the content without losing too much information? Is it possible to automate this process and avoid time-consuming human reviews? I know it would be difficult to apply classical NLP techniques (e.g., TF-IDF, Spell Checkers, Named Entity Recognition, …) with this variety of answers, and this is where [ChatGPT API](https://openai.com/blog/introducing-chatgpt-and-whisper-apis) comes to the rescue!

#### Lessons Learned:

- **Open-ended questions are much more expressive than close-ended ones**. Since LLM is a new topic, the survey gave a lot of freedom to its participants to share feedback without imposing pre-defined answers.
- **Open-ended questions are hard to systematically analyze and visualize.** While this type of answer is difficult to summarize, the survey gave me a good excuse to play with ChatGPT and assist the MLOps Community.
- **Besides ChatGPT, I don’t think there is a solution to handle the MLOps survey at scale**. Plan B was to combine several NLP techniques, but I was pretty sure it would take as much time to develop as it would take me to review the answers manually. To quote the XKCD chart of automation:

![Automation: https://xkcd.com/1319/](/static/img/articles/fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned/02.webp)

Automation: [https://xkcd.com/1319/](https://xkcd.com/1319/)

### Cleaning the survey with ChatGPT API

The survey analysis was my first time developing with [ChatGPT API](https://platform.openai.com/docs/api-reference). I thought it would be a good match since the task was open-handed and required a lot of background knowledge to find and extract the information. On the other hand, I didn’t want to use or fine-tune smaller LLMs to avoid the pitfalls of creating a new model for a one-shot task.

To get more background on prompt engineering, I read the [Prompting Guide](https://www.promptingguide.ai/) and the [Open AI Cookbook](https://github.com/openai/openai-cookbook) before jumping on this task. I found out that the API was easy to use, especially compared to more complex libraries such as deep learning frameworks. Moreover, it seems intuitive to express requirements in natural language. My main struggle was to understand how to convert ChatGPT outputs to programming data structures with Python.

I used [Google Colab](https://colab.research.google.com/) to clean up the survey. [The notebook can be accessed at this address](https://colab.research.google.com/drive/1UNWv3ehNZUUcLRBTAX5xBkCYxWnYsBRi#scrollTo=cbI7Qshr9Bqp). In the rest of this section, I’m going to highlight the main structures that helped me work on this use case.

[**Google Colaboratory**\
*MLOps Survey: Preparation Notebook*colab.research.google.com](https://colab.research.google.com/drive/1UNWv3ehNZUUcLRBTAX5xBkCYxWnYsBRi#scrollTo=cbI7Qshr9Bqp "https://colab.research.google.com/drive/1UNWv3ehNZUUcLRBTAX5xBkCYxWnYsBRi#scrollTo=cbI7Qshr9Bqp") [](https://colab.research.google.com/drive/1UNWv3ehNZUUcLRBTAX5xBkCYxWnYsBRi#scrollTo=cbI7Qshr9Bqp)

The code snippet below shows the [Open AI model](https://platform.openai.com/docs/api-reference/models) used for this experiment. The [“gpt-3.5-turbo” corresponds to the same model used by the ChatGPT application](https://zapier.com/blog/chatgpt-vs-gpt/). The [ChatGPT API](https://platform.openai.com/docs/api-reference/chat) exposed [a single endpoint to create chat completions from user messages](https://platform.openai.com/docs/api-reference/chat) (i.e., POST [https://api.openai.com/v1/chat/completions](https://api.openai.com/v1/chat/completions)).

```json
{
  "created": 1677610602,
  "id": "gpt-3.5-turbo",
  "object": "model",
  "owned_by": "openai",
  "parent": null,
  "permission": [
    {
      "allow_create_engine": false,
      "allow_fine_tuning": false,
      "allow_logprobs": true,
      "allow_sampling": true,
      "allow_search_indices": false,
      "allow_view": true,
      "created": 1683391732,
      "group": null,
      "id": "modelperm-Kch774kyIWxK1SMaTV7JKoho",
      "is_blocking": false,
      "object": "model_permission",
      "organization": "*"
    }
  ],
  "root": "gpt-3.5-turbo"
}
```

I used the following function to associate the user inputs with the model outputs. The function takes as arguments 1) the ChatGPT model, 2) the instructions to perform the task in natural language, 3) the user inputs from a single column, and 4) the size of the batch (i.e., how many user inputs are processed at a time). The function then converts the instructions and input batch to [ChatGPT messages and sends them to the API endpoint](https://platform.openai.com/docs/api-reference/chat). Finally, the model output is parsed to Python data structures and combined into a dataframe.

```python
def associate(model, instructions: str, inputs: pd.Series, batch_size: int = 20, limit: int | None = None, **kwargs) -> pd.DataFrame:
    """Associate the user inputs to the model outputs with the given instructions."""
    # avoid wasting requests
    requests = inputs.dropna()
    # apply the limit (optional)
    if limit is not None:
        requests = requests[:limit]
    print('- Inputs:', len(inputs))
    # iterate on the requests by batch
    dataframes = [] # store partial results
    for i, subset in batch(requests, batch_size):
        print('- batch:', i, '->', len(subset))
        # query the model and extract the records
        messages = chat(instructions, subset.tolist())
        content = query(model, messages=messages)
        records = from_jsonlines(content)
        # handle the case where lengths are different
        if len(records) != len(subset):
            print(f'Warning! Got: {len(records)}, expected: {len(subset)}')
            records = records + [{} for i in range(len(subset) - len(records))]
        # convert the records to an indexed dataframe
        df = pd.DataFrame(records, index=subset.index)
        dataframes.append(df)
    # combine the results with the inputs
    outputs = pd.concat(dataframes, axis='index')
    reviews = pd.concat([inputs, outputs], axis='columns')
    return reviews
```

The text snippet below shows the prompt associated with Question 3: “What is your use case/use cases?”. The first four sentences described the task to be done by ChatGPT. The next two instructions explain the output format for the model. For simplicity's sake, I choose to use [JSON lines](https://jsonlines.org/) (i.e., JSON records separated by newlines) to easily parse the output with Python. Ultimately, the last sentences give an example of the expected input and output of the model.

Here we can see that the task is quite complex, as the model needs to understand both the fields associated with the answer (e.g., analyze logs -\> Computer Security) and find common NLP tasks from the inputs (e.g., question and classify text -\> Questions Answering, Text Classification).

```text
I received answers from an MLOps survey about Large Language Models (LLMs).
Your task is to extract all the Natural Language Processing (NLP) tasks and industry fields from each answer.
You should use common NLP tasks and industry fields whenever possible to avoid synonyms and acronyms.
If no tasks or fields are mentioned, you should use an empty string as a placeholder.
You should output these information in the JSON lines format.
You should generate one JSON line per answer.
Here's an example of an answer:
- analyze logs to answer questions and classify text
Here's an example of the expected output:
{"fields": "Computer Security", "tasks": "Question Answering, Text Classification"}
Answers:
```

#### Lessons Learned:

- **ChatGPT API is easy to use but hard to integrate**. You must be creative to connect the task that you are trying to automate with the rest of the pipeline. In this case, I use JSON lines to integrate the model output.
- **Prompt templates are useful to avoid repetition**. I had to copy-paste a lot of prompts for each question. I think a tool like [LangChain](https://python.langchain.com/en/latest/index.html) could help avoid such unnecessary repetitions in the future.
- **ChatGPT outputs are difficult to evaluate without manual reviews**. I now understand why practitioners struggle to properly evaluate LLMs. I was able to use my human capacities in this case, but what about more complex tasks or with more user inputs?
- [**Reproducibility can be controlled easily by setting temperature = 0**](https://gptforwork.com/guides/openai-gpt3-temperature). Initially, I was concerned that the model output would vary too much. Fortunately, you can change the temperature to avoid randomness in the model responses.
- [**The ChatGPT API lacks a good batch option**](https://community.openai.com/t/batching-with-chatcompletion-not-possible-like-it-was-in-completion/81647) **to improve performance**. Concretely, you can’t use the array of messages supported by the API to provide one user input per message (or at least, I was not able to use it in my case). **Nearly all my problems with the ChatGPT API came from this point alone.**

### Manual Reviews and Visualizations

During my development, I found out that ChatGPT gave me good results 80% of the time. Still, this was not sufficient to ship the model output as-is. Thus, I performed a manual review of all the user answers, which was clearly the most tedious part of the whole experience …

Out of this manual review, the most common errors I found were:

- The number of model outputs doesn’t match the number of user inputs
- ChatGPT hasn’t extracted all the information that I wanted
- The model outputs were shifted by one or more value

On the other hand, I found some pretty impressive benefits:

- Nearly all model results added some value over the raw user answer
- The model errors were quick to fix during the manual review
- Expressing intents from natural language is accessible

Following my manual review, I created [another notebook](https://colab.research.google.com/drive/1vQHEvKqedyJW4re9nzp7GlgjKundzVjb#scrollTo=Gd0pr38hoT7S) to visualize the results of the survey. You can also find [the spreadsheet generated by ChatGPT at this address](https://docs.google.com/spreadsheets/d/1c7PHCQ2mgOJnYbsP2PAr4MRh2VBrqJDy/edit#gid=362297934), and [the spreadsheet reviewed manually at this address](https://docs.google.com/spreadsheets/d/1_0xLS96xyZmu1EE1Xcrf9zy7Tte8OFyp/edit#gid=362297934).

[**Google Colaboratory**\
*MLOps Survey: Visualization Notebook*colab.research.google.com](https://colab.research.google.com/drive/1vQHEvKqedyJW4re9nzp7GlgjKundzVjb#scrollTo=Gd0pr38hoT7S "https://colab.research.google.com/drive/1vQHEvKqedyJW4re9nzp7GlgjKundzVjb#scrollTo=Gd0pr38hoT7S") [](https://colab.research.google.com/drive/1vQHEvKqedyJW4re9nzp7GlgjKundzVjb#scrollTo=Gd0pr38hoT7S)

Let’s now check some visualizations to better grasp the final results. The following figures show the answers to Question 4: “Have you integrated or built any internal tools to support LLMs in your org? If so what?”. The users provided two types of information: the purpose for integrating LLMs (first figure), and the tools used to support the integration (second figure).

![Question 4 (Purposes): Have you integrated or built any internal tools to support LLMs in your org? If so what?](/static/img/articles/fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned/03.webp)

Question 4 (Purposes): Have you integrated or built any internal tools to support LLMs in your org? If so what?

![Question 4 (Solutions): Have you integrated or built any internal tools to support LLMs in your org? If so what?](/static/img/articles/fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned/04.webp)

Question 4 (Solutions): Have you integrated or built any internal tools to support LLMs in your org? If so what?

#### Lesson Learned:

- **Integration was trivial with JSON Lines**. I love the capacity of ChatGPT to output both natural language and code with the same system.
- **ChatGPT has excellent summarization capabilities**. It was able to summarize complex sentences in a few standard keywords with ease.
- **Having a good pipeline is key for iterating quickly on the use case**. This is why my first notebook has several helper functions to manipulate ChatGPT API with ease.

### Evaluations and Conclusions

For the final step, I wanted to evaluate the performance of ChatGPT compared to my manual review. To do so, I extracted the values from the spreadsheet 1) based on the raw output of ChatGPT API and 2) following my manual review. I then performed a side-by-side comparison of all values.

**Evaluation Process**:

- Exclude cases where both values are missing -\> 0
- When ChatGPT and I disagreed (strict inequality) -\> -1
- When ChatGPT and I agreed (strict equality, excluding missing) -\> +1

You can find [the evaluation notebook at the following address](https://colab.research.google.com/drive/17WViQH-qTVec1okQHqGywndwxXWW52WJ#scrollTo=P_CE_SXMmBLO). Note that this is a harsh evaluation for ChatGPT, as I didn’t take into consideration results that are partially good. Either the model gave good results (+1), or I had to change something to get the desired results (-1). There is no in-between, even if the model provides some added value in the process.

[**Google Colaboratory**\
*MLOps Survey: Evaluation Notebook*colab.research.google.com](https://colab.research.google.com/drive/17WViQH-qTVec1okQHqGywndwxXWW52WJ#scrollTo=P_CE_SXMmBLO "https://colab.research.google.com/drive/17WViQH-qTVec1okQHqGywndwxXWW52WJ#scrollTo=P_CE_SXMmBLO") [](https://colab.research.google.com/drive/17WViQH-qTVec1okQHqGywndwxXWW52WJ#scrollTo=P_CE_SXMmBLO)

We can see in the plot below the number of good and bad answers per information extracted. Some information was easily fixed by ChatGPT (e.g., topics, tools, approaches, tasks, …) while others were more challenging to the model (e.g., challenges, reasons, title, …). My conclusions for this evaluation are 1) it’s easier for the model to extract common knowledge for low-variety answers (e.g., NLP tasks), and 2) high-variety answers such as titles and reasons are more diverse and thus more open to interpretation.

![Fixing the MLOps Survey on LLMs with ChatGPT API: Lessons Learned](/static/img/articles/fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned/05.webp)

The plot below shows the final evaluation of the model for my use case. Overall, ChatGPT API gave more good answers (514) than bad ones (289). Qualitatively, even bad results contained relevant values that improved the process. This made the manual review less painful than I first expected.

![Fixing the MLOps Survey on LLMs with ChatGPT API: Lessons Learned](/static/img/articles/fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned/06.webp)

#### Conclusions (for my use case):

- **ChatGPT is productive.** This work took 6 hours to develop. While it may have been less time-consuming to do a full manual review, the approach based on ChatGPT was much more enjoyable!
- **ChatGPT is cost-efficient.** This experience cost me \$0.15. I’m pleasantly surprised by how inexpensive ChatGPT is for building quick prototypes.
- **ChatGPT was accurate enough.** Whenever the model outputs were good or bad, they provided significant help to the review process.

#### Extrapolations (for other use cases):

- **The sweet spot for ChatGPT is chat applications**. [The lack of good batch options was hard to overcome](https://community.openai.com/t/batching-with-chatcompletion-not-possible-like-it-was-in-completion/81647). I think ChatGPT is better suited for interactive use cases, such as [the application provided by default](https://chat.openai.com/chat).
- **ChatGPT is a great tool for building quick prototypes**. Fine-tuning smaller models might be more efficient at dealing with specific use cases. Thus, I think ChatGPT is analogous to [Auto ML for machine learning](https://www.automl.org/book/): great for prototyping, but limited in exploring problems in-depth.
- **Integration and fine-tuning are important for reliability**. This is good news for our community, as this means ML and MLOps engineers will be key in enabling use cases based on LLMs. Humans are not out of the equation yet!

![Machine Learning: https://xkcd.com/1838/](/static/img/articles/fixing-the-mlops-survey-on-llms-with-chatgpt-api-lessons-learned/07.webp)

Machine Learning: [https://xkcd.com/1838/](https://xkcd.com/1838/)
