+++
title = "Bromate: Automate Your Browser with Agentic Workflows 🧭"
description = "The AI landscape is constantly evolving, pushing the boundaries of what’s possible with technology. One of the most exciting frontiers is…"
date = "2024-09-14"
tags = ["Agent", "Project"]
slug = "bromate-automate-your-browser-with-agentic-workflows"
syndicated = "https://medium.com/@fmind/bromate-automate-your-browser-with-agentic-workflows-a3917850192c"
draft = false
+++

The AI landscape is constantly evolving, pushing the boundaries of what’s possible with technology. One of the most exciting frontiers is the rise of [**agentic workflows**](https://en.wikipedia.org/wiki/Intelligent_agent), a paradigm shift in automation that should revolutionize the way we interact with software. Imagine a world where you can simply tell your browser what you want to achieve, and it figures out the _how_ on its own, executing complex tasks with minimal human intervention. This is the power of agentic workflows, and [**Bromate**](https://github.com/fmind/bromate), an open-source Python project, is leading the charge in bringing this transformative technology to web browser automation.

![Photo by Jamie Street on Unsplash](/static/img/articles/bromate-automate-your-browser-with-agentic-workflows/cover.webp)

Photo by [Jamie Street](https://unsplash.com/@jamie452?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

### Decoding Agentic Workflows for Automation 💡

[Agentic workflows](https://en.wikipedia.org/wiki/Software_agent) represent a new level of sophistication in automation. Instead of relying on pre-programmed scripts or rigid rules, they leverage the power of large language models (LLMs) to understand user intent and dynamically generate the necessary steps to achieve a desired outcome. Think of it as having a highly skilled virtual assistant that’s capable of understanding natural language instructions and translating them into precise actions within your browser.

This approach offers several key advantages over traditional automation methods:

- **Intuitive Interaction** 🔃**:** Agentic workflows bridge the gap between human intent and machine execution, allowing users to interact with software in a more natural and intuitive way.
- **Flexibility and Adaptability** ➰**:** LLMs can handle variations in user input and adapt to changes in the environment, making agentic workflows more robust and versatile than rule-based systems.
- **Reduced Development Time** ⌛**:** By automating the process of creating automation workflows, agentic workflows free up developers to focus on more complex and strategic tasks.

### Bromate: Your Agentic Browser Automation Companion ⚙️

[**Bromate**](https://github.com/fmind/bromate) is an open-source experiment designed to bring the power of agentic workflows to web browser automation. It provides a framework that allows developers to run scripts capable of understanding user queries and executing actions within a browser environment.

**Here’s how Bromate works:**

1. **User Query** ❗**:** You provide Bromate with a natural language query describing the task you want to automate, such as “Fill out the registration form on this website.”
2. **Workflow Generation** ✦**:** Bromate’s LLM analyzes the query and generates a workflow consisting of a series of actions that need to be performed in the browser.
3. **Action Execution** 🔥**:** Bromate’s agent executes the workflow, interacting with the browser using Selenium to perform actions like clicking buttons, filling out forms, and navigating pages.
4. **Feedback Loop** ⟳**:** After each action, Bromate captures the browser’s state (screenshot and page source) and feeds it back to the LLM, allowing it to refine the workflow and make adjustments as needed.

[**Bromate Actions**](https://github.com/fmind/bromate/blob/main/src/bromate/actions.py) are defined in Python, like in the two functions below:

```python
@declare(
    schema=agents.Schema(
        type=agents.Type.OBJECT,
        properties={
            "url": agents.Schema(type=agents.Type.STRING, description="URL of the web page to open")
        },
        required=["url"],
    )
)
def get(driver: drivers.Driver, config: ActionConfig, url: str) -> agents.Structure:
    """Open a web page in the browser window."""
    driver.get(url=url)  # wait loading
    time.sleep(config.sleep_time)
    return agents.Structure(
        name=get.__name__,
        response={
            "title": driver.title,
            "url": driver.current_url,
            "page_source": driver.page_source,
        },
    )


@declare(
    schema=agents.Schema(
        type=agents.Type.OBJECT,
        properties={
            "css_selector": agents.Schema(
                type=agents.Type.STRING, description="CSS selector of the element to click on."
            ),
        },
        required=["css_selector"],
    )
)
def click(driver: drivers.Driver, config: ActionConfig, css_selector: str) -> agents.Structure:
    """Click on an element given its CSS selector."""
    element = driver.find_element(by=drivers.CSS, value=css_selector)
    element.click()
    time.sleep(config.sleep_time)
    return agents.Structure(
        name=click.__name__,
        response={
            "title": driver.title,
            "url": driver.current_url,
            "page_source": driver.page_source,
        },
    )
```

### Gemini: The Brain Behind Bromate’s Agentic Power 🧠

Bromate leverages the power of [**Google’s Gemini models**](https://ai.google.dev/gemini-api), a family of advanced LLMs, to implement its agentic workflows. Gemini’s ability to understand natural language and generate contextually relevant responses makes it an ideal choice for powering Bromate’s core functionality.

Here’s the core algorithm showing how Gemini is integrated into Bromate:

```python
from bromate import actions, agents, drivers, types

def execute(
    query: str,
    agent: agents.Agent,
    driver: drivers.Driver,
    config: ExecutionConfig,
    action_config: actions.ActionConfig,
    agent_functions: list[agents.Function] = actions.AGENT_FUNCTIONS,
) -> Execution:
    """Execute a query given a config."""
    # contents
    query_content = agents.Content(role=agents.Role.USER.value, parts=[agents.Part(text=query)])
    contents = [query_content]
    # tools
    agent_tool = agents.Tool(function_declarations=agent_functions)
    tools = [agent_tool]
    # steps
    while True:
        done = False
        # response
        response = agent.generate_content(contents=contents, tools=tools)
        # parts
        structures: list[agents.Structure] = []
        for i, part in enumerate(response.parts, start=1):
            if call := part.function_call:
                name, kwargs = call.name, call.args
                if name in config.stop_actions:
                    done = True  # stop execution
                if action := getattr(actions, name):
                    try:
                        structure = action(driver=driver, config=action_config, **kwargs)
                    except Exception as error:
                        kwargs_text = ", ".join(f"{key}={val}" for key, val in kwargs.items())
                        logger.error(
                            f"Error while executing action '{name}' with kwargs '{kwargs_text}': {error}"
                        )
                        structure = agents.Structure(name=name, response={"error": str(error)})
                    structures.append(structure)
                else:
                    raise ValueError(f"Cannot execute action (unknown action name): {name}!")
            elif part.text:
                pass
            else:
                raise ValueError(f"Cannot handle agent response (unknown part type): {part}!")
        # output
        agent_content = agents.Content(role=agents.Role.AGENT.value, parts=response.parts)
        if done is True:
            return agent_content
        contents.append(agent_content)
        user_input = yield agent_content
        # input
        message = user_input or config.default_message
        returned = [agents.Part(function_response=s) for s in structures]
        screenshot = agents.Blob(mime_type="image/png", data=driver.get_screenshot_as_png())
        user_content = agents.Content(
            role=agents.Role.USER.value,
            parts=[
                agents.Part(inline_data=screenshot),
                agents.Part(text=message),
            ]
            + returned,  # action calls
        )
        contents.append(user_content)
```

### A Deep Dive into Bromate’s Architecture 🧰

Bromate’s architecture is built on a foundation of powerful tools and libraries:

- [**Google’s Generative AI Platform**](https://ai.google.dev/gemini-api) **:** Bromate leverages [Google’s Gemini models](https://deepmind.google/technologies/gemini/) for its LLM capabilities, enabling it to understand user queries and generate workflows.
- [**Selenium**](https://selenium-python.readthedocs.io/) **:** This popular [browser automation framework](https://www.testim.io/blog/browser-test-automation/) provides the necessary tools for Bromate’s agent to interact with web browsers.
- [**Pydantic**](https://docs.pydantic.dev/latest/) **:** This data validation library ensures that Bromate’s configurations and data structures are well-defined and consistent.
- [**Loguru**](https://loguru.readthedocs.io/en/stable/) **:** This logging library provides detailed insights into Bromate’s execution process, facilitating debugging and monitoring.

![External Systems and Modules of the Bromate project](/static/img/articles/bromate-automate-your-browser-with-agentic-workflows/02.webp)

External Systems and Modules of the Bromate project

### Getting Started with Bromate 🔋

Bromate is easy to install and use. The [project’s README](https://github.com/fmind/bromate/blob/main/README.md) provides a comprehensive guide on setting up your environment and running your first automated queries.

**Here’s a simple example of how to use Bromate:**

```bash
# Install Bromate using pip
pip install bromate
# Export you Gemini API key
export GOOGLE_API_KEY=...

# Example 1: Subscribe to the MLOps Community Newsletter
bromate "Open the https://MLOps.Community website.
Click on the 'Join' link. Write the address 'hello@mlops'"
```

```bash
# Example 2: Summarize the features of the next Python release
bromate --interaction.stay_open=False \
--agent.name "gemini-1.5-pro-latest" \
"Go to Python.org. Click on the downloads page.
Click on the PEP link for the future Python release.
Summarize the release schedule dates."
```

You can explore Bromate options on the [project README.md file](https://github.com/fmind/bromate) or by typing `bromate -h` in your shell.

### Limitations and Future Directions 🚧

- **Accuracy vs. Speed:** Sending full browser context (screenshots and source code) to the LLM after every action can be slow. Bromate optimizes this by sending source code only when needed (e.g., on page change).
- **Instruction Granularity:** Users may need to provide detailed instructions in some cases. Future development will explore techniques like “chain of thought” prompting to enhance the LLM’s ability to plan multi-step actions.
- **Action Selection and CSS Selectors:** LLMs can sometimes choose incorrect actions or hallucinate CSS selectors. Bromate uses a retry mechanism with error feedback to improve accuracy.
- **File Downloads:** File download support is not yet implemented. Contributions are welcome!

We are actively working to address these limitations and expand Bromate’s capabilities. Your feedback and contributions are invaluable to improve the project!

### Embracing the Agentic Future 💪

Agentic workflows are transforming the way we think about automation. [**Bromate**](https://github.com/fmind/bromate) provides a powerful and accessible platform for exploring the potential of this exciting technology in the context of web browser automation. By embracing agentic workflows, developers and businesses can unlock new levels of efficiency, productivity, and innovation.

**Join the** [**Bromate community**](https://github.com/fmind/bromate) **and be part of the agentic revolution!**

![Photo by Jacek Dylag on Unsplash](/static/img/articles/bromate-automate-your-browser-with-agentic-workflows/03.webp)

Photo by [Jacek Dylag](https://unsplash.com/@dylu?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)
