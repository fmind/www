+++
title = "Slides-To-Translate: When IT Says No, Build a $0.04 Solution on Your Lunch Break"
description = "It is a classic tale of corporate life. A colleague of mine at Decathlon had a mammoth task: translate a 155-slide presentation into several languages."
date = "2025-07-29"
tags = ["LLM", "Demo"]
slug = "slides-to-translate-when-it-says-no-build-a-0-04-solution-on-your-lunch-break"
syndicated = "https://medium.com/@fmind/slides-to-translate-when-it-says-no-build-a-0-04-solution-on-your-lunch-break-3afa8bd9f6bb"
draft = false
+++

### **Slides-To-Translate:** When IT Says No, Build a \$0.04 Solution on Your Lunch Break

It is a classic tale of corporate life. A colleague of mine at Decathlon had a mammoth task: **translate a 155-slide presentation into several languages**. In a global company, this is a daily reality. The content was ready, the deadline was looming, but the path forward was blocked.

The usual suspects — approved [Chrome](https://chromewebstore.google.com/category/extensions) and [Workspace](https://workspace.google.com/marketplace/) extensions that could automate this — were unfortunately blocked by our organization’s IT policy. Have you ever tried requesting a new tool in a large company? It often feels like sending a message in a bottle into the cosmic ocean. My colleague’s request had, predictably, vanished into a bureaucratic black hole.

She was stuck. Manually translating 155 slides is not just tedious; it’s a recipe for errors and missed deadlines! We had seen several similar requests before, but no viable solution was ever found, leaving colleagues to manually copy and paste text from Google Translate …

Listening to her predicament, I thought, “There has to be a faster way.” During my lunch break, I decided to take a crack at it. I figured hacking together a quick solution would be faster than waiting for a permission slip.

![Source: Gemini App](/static/img/articles/slides-to-translate-when-it-says-no-build-a-0-04-solution-on-your-lunch-break/cover.webp)

Source: Gemini App

**And it was. In less than an hour, I had a working solution.**

### The Power Trio: Gemini, Colab, and Vertex AI 🤖✨

My toolkit for this lunch-break challenge was simple but powerful:

- 💻 [**Google Colab**](https://colab.research.google.com/): For a ready-to-go coding environment.
- ☁️ [**Vertex AI**](https://cloud.google.com/vertex-ai/generative-ai/docs): To access Google’s powerful suite of AI models.
- ⚡️ [**Gemini 2.5 Flash**](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash): The star of the show. A fast, multimodal, and incredibly cost-effective model perfect for a task like this.

The plan was straightforward: use the [Google Slides](https://developers.google.com/workspace/slides/api/guides/overview) and [Drive APIs](https://developers.google.com/workspace/drive/api/guides/about-sdk) to read the presentation, send the text to Gemini for translation, and then write the translated text back to a new copy of the slide deck.

A little bit of coding, especially when supercharged by an AI assistant, can go a very, very long way.

### How it Works: A Peek Under the Hood ⚙️

The solution is a single [Google Colab notebook](https://colab.research.google.com/drive/18FOakT2-IdhebVNPyiKYdbJWgrUyXqU-#scrollTo=ICBTF6Y_Trle) that automates the entire process. For anyone curious, here’s the gist of it.

First, you need to authenticate and set up the environment. This is surprisingly easy in Colab:

```python
# Authenticate with your Google Cloud Project
from google.colab import auth
auth.authenticate_user(project_id="your-gcp-project-id")

# Build the service clients for Drive and Slides
from googleapiclient.discovery import build
drive_service = build('drive', 'v3')
slides_service = build('slides', 'v1')

# And initialize the Vertex AI client
from google import genai
client = genai.Client(vertexai=True)
```

After creating a safe copy of the presentation and extracting all the unique text strings, the real magic begins. To make the translation process fast, I used a [`ThreadPoolExecutor`](https://docs.python.org/3/library/concurrent.futures.html#threadpoolexecutor) to make concurrent API calls to the Gemini model.

The core translation function is simple. It takes a piece of text and a set of instructions, then returns the translation.

```python
def translate_text(text):
    """Translates a single text string."""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=instructions, # e.g., "Translate to German..."
                temperature=0.0,
            )
        )
        return text, response.text.strip()
    except Exception as error:
        print(f"Error translating '{text}': {error}")
        return text, None
```

This function is then called in parallel for every unique piece of text from the slides:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

# Use ThreadPoolExecutor for concurrent translation
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    # Create a future for each text translation
    futures = [executor.submit(translate_text, text) for text in unique_texts]
    for future in as_completed(futures):
        # Collect the results as they complete
        text, translation = future.result()
        translations[text] = translation
```

Once all the text is translated, the final step is to replace the original text in the copied presentation. This is done by creating a batch of [`replaceAllText`](https://developers.google.com/workspace/slides/api/reference/rest/v1/presentations/request#replacealltextrequest) requests for the [Google Slides API](https://developers.google.com/workspace/slides/api/guides/overview). The requests are sorted from longest to shortest string to prevent issues where a shorter piece of text might be a substring of a longer one.

```python
requests = []
sorted_translations = sorted(translations.items(), key=lambda item: len(item[0]), reverse=True)
for text, translation in sorted_translations:
    if translation.strip():
        requests.append({
            'replaceAllText': {
                'replaceText': translation,
                'pageObjectIds': list(page_ids), # The slides where the text appears
                'containsText': {
                    'text': text,
                    'matchCase': True,
                }
            }
        })

# Execute the batch update
body = {'requests': requests}
response = slides_service.presentations().batchUpdate(
    presentationId=copied_presentation_id, body=body
).execute()
```

The result? A perfectly translated slide deck, ready to go.

![Screenshot of the Luxembourgish Version](/static/img/articles/slides-to-translate-when-it-says-no-build-a-0-04-solution-on-your-lunch-break/02.webp)

Screenshot of the Luxembourgish Version

### See it in Action 🚀

Want to see the results for yourself? While I can't share corporate slides publicly, I can use some slides I wrote for an [MLOps Community Meetup](https://mlops.community/). Here are the original presentation and the versions translated by the script:

- 📊 **Original Presentation**: [https://docs.google.com/presentation/d/1CvmBW0BmorHpC6NwYCh94qTAMZY9MlUx7ClcSwCg7Dg/edit?slide=id.p#slide=id.p](https://docs.google.com/presentation/d/1CvmBW0BmorHpC6NwYCh94qTAMZY9MlUx7ClcSwCg7Dg/edit?slide=id.p#slide=id.p)
- 🇫🇷 **Translated to French**: [https://docs.google.com/presentation/d/1t7MqZG5BUCbTbDKlOu25e0BLi00IIIcFVWKZCCt8h2o/edit?slide=id.p#slide=id.p](https://docs.google.com/presentation/d/1t7MqZG5BUCbTbDKlOu25e0BLi00IIIcFVWKZCCt8h2o/edit?slide=id.p#slide=id.p)
- 🇩🇪 **Translated to German**: [https://docs.google.com/presentation/d/1jYGc7bqus-Kluvmww5U8T3WgALDayh5cfsYgJPiA6ds/edit?slide=id.p#slide=id.p](https://docs.google.com/presentation/d/1jYGc7bqus-Kluvmww5U8T3WgALDayh5cfsYgJPiA6ds/edit?slide=id.p#slide=id.p)
- 🇱🇺 **Translated to Luxembourgish**: [https://docs.google.com/presentation/d/1vcmMHp_vh1pMhNgLMlVyGC_wRJawtY9-\_g8T1df5Hfo/edit?slide=id.p#slide=id.p](https://docs.google.com/presentation/d/1vcmMHp_vh1pMhNgLMlVyGC_wRJawtY9-_g8T1df5Hfo/edit?slide=id.p#slide=id.p)

### The Jaw-Dropping Part: The Cost 💰

This is where the story goes from “cool project” to “game-changer.”

**For my colleague’s 155-slide deck, the total cost of using** [**Gemini 2.5 Flash**](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash) **through Vertex AI was a minuscule \$0.04.**

_Let that sink in. Four cents to solve a problem that was holding up a project and causing a major headache._

To put it in perspective, I ran the numbers on [my smaller 22-slide test presentation](https://docs.google.com/presentation/d/1CvmBW0BmorHpC6NwYCh94qTAMZY9MlUx7ClcSwCg7Dg/edit?slide=id.p#slide=id.p):

- 📥 Total Input Tokens: 15,088
- 📤 Total Output Tokens: 1,687
- 💵 Input Cost: \$0.0045
- 💸 Output Cost: \$0.0042
- 🧾 **Total Cost**: \$0.0087

**That’s less than a single cent!** The cost is so low it’s practically a rounding error.

### Key Benefits of this Approach 🗝️

Beyond the speed and low cost, this DIY solution has several powerful advantages over external products:

- 🔒 **Corporate Data Stays Secure**: Because the solution uses Vertex AI, which was already an approved platform within our organization, no sensitive corporate data ever leaves our GCP environment. This is a massive win for security and compliance.
- 💲 **Highly Cost-Effective**: Compared to the subscription fees for many third-party translation services, this method is orders of magnitude cheaper. You only pay for what you use, which for this task is next to nothing.
- 🔄 **Infinitely Reusable & Adaptable**: Now that the basic framework is in place (Colab + Vertex AI + GCP APIs), it can be adapted for [countless other use cases](https://github.com/fmind?tab=repositories). Automating reports, summarizing documents, analyzing feedback — the possibilities are endless.
- 🎨 **Fully Customizable Prompts**: You have complete control over the prompt sent to the AI. This means you can guide the translation style, provide specific context about the content, and fine-tune the output in a way that black-box products simply don’t allow.

### Potential Areas for Improvement 🌱

While the solution worked, there’s always room for refinement. Here are a few ideas for taking it to the next level:

- ⏩ **Optimize API Calls**: Instead of sending one translation request per text element, the code could be optimized to batch multiple requests into a single API call, which would further reduce latency and avoid repeating system instructions.
- 🧠 **Provide More Context**: The model could be given even more context, such as the slide number or surrounding text, to produce even more accurate and contextually-aware translations.
- 🖼️ **Translate Text in Images**: The current version only handles text boxes. A more advanced, experimental version could use a multimodal model like Gemini to identify and translate text embedded within images on the slides.

### The Real Lesson: Empowerment Through Technology 🎓

This little lunch-break project is a perfect example of the world we live in now. On one hand, we have the rigid structures of large organizations, which can be slow to adapt. On the other, we have generative AI tools that empower any individual with a bit of technical skill to build incredibly powerful and efficient solutions in minutes.

We no longer have to wait for permission. With tools like Gemini and platforms like Vertex AI, we can solve our own problems, and our colleagues’ problems, with a speed and cost-efficiency that would have been unimaginable just a few years ago.

So next time you’re stuck waiting on a process, maybe ask yourself: “Could I just build this myself?” You might be surprised by what you can accomplish before you’ve even finished your sandwich!

_You can find the full project and notebook on GitHub here:_ [https://github.com/fmind/slides-to-translate/](https://github.com/fmind/slides-to-translate/) _._

![Source: Gemini App](/static/img/articles/slides-to-translate-when-it-says-no-build-a-0-04-solution-on-your-lunch-break/03.webp)

Source: Gemini App
