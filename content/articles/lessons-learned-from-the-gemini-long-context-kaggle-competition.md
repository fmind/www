+++
title = "Lessons Learned from the Gemini Long Context Kaggle Competition 🧠"
description = "Explored Gemini’s long context in a Kaggle competition. Key lessons learned about its potential and limitations."
date = "2025-02-07"
tags = ["LLM", "Demo"]
slug = "lessons-learned-from-the-gemini-long-context-kaggle-competition"
syndicated = "https://medium.com/@fmind/lessons-learned-from-the-gemini-long-context-kaggle-competition-95381d38f303"
draft = false
+++

The world of Generative AI is constantly evolving, and one of the most exciting frontiers is the expansion of model's [long context window](https://cloud.google.com/vertex-ai/generative-ai/docs/long-context). Think of a context window as an AI model’s short-term memory — how much information it can hold and process at once. For years, [this has been a major limitation](https://www.perplexity.ai/page/context-window-limitations-of-FKpx7M_ITz2rKXLFG1kNiQ). Traditional models could only juggle a few thousand “tokens” (pieces of words), making it hard for them to understand complex documents, long conversations, or intricate codebases.

![Photo by Greg Rakozy on Unsplash](/static/img/articles/lessons-learned-from-the-gemini-long-context-kaggle-competition/cover.webp)

Photo by [Greg Rakozy](https://unsplash.com/@grakozy?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

Then came [Google’s Gemini 1.5](https://blog.google/technology/ai/google-gemini-next-generation-model-february-2024/), boasting a game-changing context window of up to **2 million tokens**. That’s like remembering 16 average novels! 🤯 This breakthrough opens up a world of possibilities, and the recent “[Gemini Long Context](https://www.kaggle.com/competitions/gemini-long-context)” Kaggle competition was a chance to explore them. I decided to jump in, and the experience was a fascinating deep dive into the potential — and the current limitations — of this cutting-edge technology.

### The Challenge: Pushing AI’s Memory to the Limit 🏋️‍♀️

The competition’s goal was simple but ambitious: create a compelling demonstration of Gemini 1.5’s long context capabilities. We were encouraged to think outside the box, showcasing use cases that would be impossible with older, smaller-context models. The Deepmind team had already provided some [impressive demos](https://blog.google/technology/ai/google-gemini-next-generation-model-february-2024/#context-window). For instance, Gemini 1.5 was able to create documentation by seeing an entire code base and was able to answer questions correctly after “watching” the movie Sherlock JR.

![https://blog.google/technology/ai/google-gemini-next-generation-model-february-2024](/static/img/articles/lessons-learned-from-the-gemini-long-context-kaggle-competition/02.webp)

[https://blog.google/technology/ai/google-gemini-next-generation-model-february-2024](https://blog.google/technology/ai/google-gemini-next-generation-model-february-2024)

### My Approach: Building an Interactive Open Textbook Experience 📚

I decided to focus on a problem close to my heart: education. ❤ Traditional textbooks are valuable resources, packed with expert knowledge and detailed examples. But they have inherent limitations:

- **Lack of Interaction:** You can’t ask a textbook a question.
- **No Personalization:** The textbook doesn’t adapt to your learning style or specific needs.
- **Difficult to Combine:** Mixing and matching content from multiple textbooks is cumbersome.

My idea was to use Gemini 1.5’s massive context window to create an “interactive textbook” experience. Imagine being able to chat with a textbook, ask clarifying questions, and receive personalized explanations — all grounded in the textbook’s content. The goal was to combine strengths of the textbook and [Gemini Long Context](https://www.kaggle.com/competitions/gemini-long-context).

![So many textbooks, so much knowledge scattered around …](/static/img/articles/lessons-learned-from-the-gemini-long-context-kaggle-competition/03.webp)

So many textbooks, so much knowledge scattered around …

### The Process: From PDFs to Personalized Learning 📄➡️🎓

My [competition code](https://www.kaggle.com/datasets/freaxmind/open-textbook-library/) followed these key steps:

1. **Dataset Selection:** I leveraged the [Open Textbook Library](https://open.umn.edu/opentextbooks), a fantastic resource with over 1,500 freely licensed textbooks. This provided a rich and diverse knowledge base.
2. **Retrieval:** I built a retrieval system using Gemini itself. Given a user’s learning goal (e.g., “I want to learn about Mathematics and Computer Science with Python”), the model would identify the most relevant textbooks from the library.
3. **Text Extraction:** I used pypdf to extract the text content from the selected textbooks. This is where the long context window really shines — I could feed entire textbooks directly into Gemini.
4. **Assistant Creation:** I crafted a system instruction for Gemini, turning it into a “friendly and helpful learning assistant”. This instruction emphasized personalization, grounding responses in the textbook content, and maintaining a pedagogic tone.
5. **Context Caching:** A crucial optimization! Gemini allows you to [cache context](https://ai.google.dev/gemini-api/docs/caching?lang=python), meaning the model doesn’t have to re-process the entire textbook for every interaction. This significantly reduces costs and improves response time.

![Example of textbooks available in the Open Textbook Library Dataset](/static/img/articles/lessons-learned-from-the-gemini-long-context-kaggle-competition/04.webp)

Example of textbooks available in the [Open Textbook Library Dataset](https://www.kaggle.com/datasets/freaxmind/open-textbook-library/)

### The Good: Impressive Results and Personalized Learning ✅

The results were, in many cases, quite impressive. Here are some key wins:

- **Improved Accuracy and Relevance:** The assistant, with access to the full textbook content, consistently provided more detailed and relevant answers compared to a baseline Gemini model without that context. For example, when asked about Newton’s method for finding square roots, the assistant provided a focused Python implementation, exactly as requested, while the baseline gave a more general explanation.
- **Personalization in Action:** The assistant tailored its responses to the user’s specific request. It could explain complex concepts in simpler terms, provide relevant examples, and even generate exercises based on the textbook material.
- **Combining Knowledge:** The system could seamlessly integrate information from multiple textbooks, creating a cross-topic learning experience. For instance, when asked about leadership in a multicultural context, the assistant drew insights from multiple relevant textbooks.
- **Cost-Effectiveness with Caching:** Context caching was a game-changer. _It reduced request costs by a factor of 4_, making the system much more practical for real-world use.

**All in all, The assistant has positive gains on 10 out of 11 cases.**

![Open Textbooks with Gemini Long Context — Slide 7](/static/img/articles/lessons-learned-from-the-gemini-long-context-kaggle-competition/05.webp)

[Open Textbooks with Gemini Long Context — Slide 7](https://docs.google.com/presentation/d/1H7Kq8Ur3f76mknLcugR0ZaBFqtba6foLQS_i7KG_4Sc/edit#slide=id.g315f80125e3_0_10)

![Open Textbooks with Gemini Long Context — Slide 7](/static/img/articles/lessons-learned-from-the-gemini-long-context-kaggle-competition/06.webp)

[Open Textbooks with Gemini Long Context — Slide 7](https://docs.google.com/presentation/d/1H7Kq8Ur3f76mknLcugR0ZaBFqtba6foLQS_i7KG_4Sc/edit#slide=id.g315f80125e3_1_28)

### The Not-So-Good: Execution Time and API Quirks ❌

The journey wasn’t without its bumps. Here’s where I encountered the limitations:

- **Execution Time:** While caching helped, interacting with the assistant was still significantly slower than using the baseline model — around 25 seconds per request versus 5 seconds. This is a major hurdle for creating a truly fluid and engaging learning experience.
- **File API Challenges:** Gemini offers a File API for uploading documents directly. However, I found it unreliable with very large files (like some of the textbooks) and surprisingly slow, even with caching. Extracting text and feeding it directly to the model proved more reliable, but this highlights a need for improvements in the API’s handling of large documents.

### Lessons Learned: The Future of AI-Powered Learning 💡

This competition was a valuable learning experience. Here are my key takeaways:

- **Long Context is a Game-Changer:** The ability to process vast amounts of information opens up exciting possibilities for AI applications, particularly in education. Imagine AI tutors with encyclopedic knowledge, personalized learning paths tailored to individual student needs, and seamless integration of diverse learning resources.
- **Performance Matters:** While long context is powerful, execution time is critical for user experience. Optimizations like caching are essential, but further improvements in model speed are needed to make these applications truly interactive.
- **Beyond RAG:** The competition highlighted that with long context windows, traditional techniques like Retrieval-Augmented Generation (RAG) might become less critical. Directly feeding relevant context to the model can be surprisingly effective.

While challenges remain, the potential of long context models like Gemini 1.5 and the recently announced [Gemini 2.0](https://blog.google/technology/google-deepmind/gemini-model-updates-february-2025/) is undeniable. I’m excited to see how this technology evolves and how it will transform the way we learn.

**Links**:

- [Kaggle Competition: Google — Gemini Long Context](https://www.kaggle.com/competitions/gemini-long-context/overview)
- [Kaggle Competition: Open Textbook Library Dataset](https://www.kaggle.com/datasets/freaxmind/open-textbook-library/)
- [Kaggle Competition: Winners Announcement](https://www.kaggle.com/competitions/gemini-long-context/discussion/552419)
- [**Kaggle Competition: Competition Code**](https://www.kaggle.com/code/freaxmind/open-textbooks-with-gemini-long-context)
- [**Kaggle Competition: Final Slides**](https://docs.google.com/presentation/d/1H7Kq8Ur3f76mknLcugR0ZaBFqtba6foLQS_i7KG_4Sc/edit#slide=id.p)

![Photo by Urban Vintage on Unsplash](/static/img/articles/lessons-learned-from-the-gemini-long-context-kaggle-competition/07.webp)

Photo by [Urban Vintage](https://unsplash.com/@urban_vintage?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)
