+++
title = "How to configure VS Code for AI, ML and MLOps development in Python 🛠️️"
description = "In this article, I will outline the steps for configuring VS Code for data scientists and machine learning engineers."
date = "2023-11-23"
tags = ["Python", "Guide"]
slug = "how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python"
syndicated = "https://medium.com/@fmind/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python-%EF%B8%8F%EF%B8%8F-8582d8c6ea54"
draft = false
+++

[Visual Studio Code](https://code.visualstudio.com/) is a remarkable application. In the past, developers faced a choice between simple, lightweight [text editors](https://en.wikipedia.org/wiki/List_of_text_editors) like Vim, Atom, and Emacs or powerful yet complex [IDEs](https://en.wikipedia.org/wiki/Comparison_of_integrated_development_environments) such as PyCharm and Eclipse. I can recall a time when running my IDE (Netbeans), my browser (Firefox), and my application (Java) simultaneously on a laptop with just 512MB of RAM was a challenge. Today, with VS Code, programmers have access to a versatile, modern, powerful, open-source tool well-supported by the community.

But possessing a good tool is only the beginning. **Just as a skilled craftsman must master their tools, it’s essential for programmers to become proficient with their editor for enhanced productivity**. In this article, I will outline the steps for configuring VS Code for data scientists and machine learning engineers. I’ll start by listing extensions that augment your programming environment. Then, I will share some settings and keybindings to enhance your development experience. Finally, I’ll provide tips and tricks to boost your coding efficiency with VS Code.

![Photo by Andrew Ruiz on Unsplash](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/cover.webp)

Photo by [Andrew Ruiz](https://unsplash.com/@andrewruiz?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

### Extensions 🔌

This section lists the extensions you can install from [VS Code Marketplace](https://marketplace.visualstudio.com/VSCode).

#### A Tier: The Must

- [**donjayamanne.python-extension-pack**](https://marketplace.visualstudio.com/items?itemName=donjayamanne.python-extension-pack) **: ultimate pack for Python development: autoDocString, Python, Jinja, IntelliCode, Python Indent, Python Environment Manager, Django.**
- [**donjayamanne.python-environment-manager**](https://marketplace.visualstudio.com/items?itemName=donjayamanne.python-environment-manager): access and manage your Python environments (venv).
- [**KevinRose.vsc-python-indent**](https://marketplace.visualstudio.com/items?itemName=KevinRose.vsc-python-indent): improve the default indentation for Python files.
- [**ms-python.black-formatter**](https://marketplace.visualstudio.com/items?itemName=ms-python.black-formatter): format your code automatically.
- [**ms-python.isort**](https://marketplace.visualstudio.com/items?itemName=ms-python.isort) **:** format your import statements automatically.
- [**ms-python.mypy-type-checker**](https://marketplace.visualstudio.com/items?itemName=ms-python.mypy-type-checker): source typing for Python. Great to validate your code and communicate how it should be used.
- [**ms-python.pylint**](https://marketplace.visualstudio.com/items?itemName=ms-python.pylint): linting support for Python. Improve your code quality and avoid code smells.
- [**ms-python.python**](https://marketplace.visualstudio.com/items?itemName=ms-python.python): language support for Python (linting, debugging, code formatting, and more).
- [**ms-python.vscode-pylance**](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance): enhanced language server for Python (static checker, intellicode, …).
- [**ms-toolsai.jupyter**](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter): extension pack for Jupyter Notebooks: Keymap, Slideshow, Notebook Renderer, and Cell Tags.
- [**ms-toolsai.jupyter-keymap**](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter-keymap): keybindings from Jupyter Notebooks.
- [**ms-toolsai.jupyter-renderers**](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter-renderers): render notebook outputs (e.g., plots).
- [**ms-toolsai.vscode-jupyter-cell-tags**](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.vscode-jupyter-cell-tags): edit cell tags in notebooks (i.e., metadata used by some plugins).

#### B Tier: The Great

- [**alefragnani.project-manager**](https://marketplace.visualstudio.com/items?itemName=alefragnani.project-manager): organize, manage, and access VS Code workspaces and Git repositories.
- [**ms-azuretools.vscode-docker**](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-docker): manage and connect to Docker through VS Code.
- [**ms-kubernetes-tools.vscode-kubernetes-tools**](https://marketplace.visualstudio.com/items?itemName=ms-kubernetes-tools.vscode-kubernetes-tools): everything you need to develop Kubernetes applications from VS Code.
- [**ms-vscode-remote.remote-containers**](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers): develop your code from a Docker container instead of your local system.
- [**ms-vscode-remote.remote-ssh**](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh): connect to a remote instance for editing files and developing your project.
- [**ms-vscode-remote.remote-ssh-edit**](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh-edit): language support for SSH configuration files.
- [**ms-vscode-remote.vscode-remote-extensionpack**](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack): extension pack for remote developments: Dev Containers, Remote SSH, Remote Tunnels, WSL.
- [**ms-vscode.remote-explorer**](https://marketplace.visualstudio.com/items?itemName=ms-vscode.remote-explorer): view remote machines (SSH) and tunnels.
- [**ms-vscode.remote-repositories**](https://marketplace.visualstudio.com/items?itemName=ms-vscode.remote-repositories): remotely browse and edit git repositories.
- [**ms-vsliveshare.vsliveshare**](https://marketplace.visualstudio.com/items?itemName=MS-vsliveshare.vsliveshare): edit code from your colleague’s computer (and vice versa). Useful for collaboration and troubleshooting.
- [**mutantdino.resourcemonitor**](https://marketplace.visualstudio.com/items?itemName=mutantdino.resourcemonitor): display the resource usage of your system in the status bar (CPU, RAM, …). Always useful for data projects.
- [**njpwerner.autodocstring**](https://marketplace.visualstudio.com/items?itemName=njpwerner.autodocstring): automatically generate Python docstrings from object definitions.
- [**redhat.vscode-yaml**](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml): YAML language support. Great file format for configuring your application.
- [**streetsidesoftware.code-spell-checker**](https://marketplace.visualstudio.com/items?itemName=streetsidesoftware.code-spell-checker): highlight and fix spelling mistakes in your code.
- [**tamasfe.even-better-toml**](https://marketplace.visualstudio.com/items?itemName=tamasfe.even-better-toml): TOML language support. Improve the edition of your `pyproject.toml` file.
- [**usernamehw.errorlens**](https://marketplace.visualstudio.com/items?itemName=usernamehw.errorlens): display warnings and errors next to your code (instead of a dedicated window).
- [**VisualStudioExptTeam.vscodeintellicode**](https://marketplace.visualstudio.com/items?itemName=VisualStudioExptTeam.vscodeintellicode): AI-assisted development features for VS Code.
- [**yzhang.markdown-all-in-one**](https://marketplace.visualstudio.com/items?itemName=yzhang.markdown-all-in-one): tons of features for editing Markdown files (shortcuts, table of contents, language support, …).

#### C Tier: The Good

- [**aaron-bond.better-comments**](https://marketplace.visualstudio.com/items?itemName=aaron-bond.better-comments): highlight comments based on a prefix (e.g., \*, !, ?, TODO, …).
- [**bierner.markdown-mermaid**](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid): display [Mermaid](https://mermaid.js.org/) diagrams in Markdown. Great to share and visualize complex concepts and design decisions.
- [**christian-kohler.path-intellisense**](https://marketplace.visualstudio.com/items?itemName=christian-kohler.path-intellisense): autocomplete file paths on your system.
- [**dchanco.vsc-invoke**](https://marketplace.visualstudio.com/items?itemName=dchanco.vsc-invoke): execute [Invoke](https://www.pyinvoke.org/) tasks from VS Code (alternative to [GNU Make](https://www.gnu.org/software/make/manual/make.html)).
- [**donjayamanne.githistory**](https://marketplace.visualstudio.com/items?itemName=donjayamanne.githistory): visualize your Git history (files, branches, commits, …).
- [**eamodio.gitlens**](https://marketplace.visualstudio.com/items?itemName=eamodio.gitlens): enhance your git experience (e.g., git blame, code lens, …).
- [**GitHub.remotehub**](https://marketplace.visualstudio.com/items?itemName=GitHub.remotehub): remotely browse and edit GitHub repositories.
- [**github.vscode-github-actions**](https://marketplace.visualstudio.com/items?itemName=GitHub.vscode-github-actions): manage GitHub Actions workflows from VS Code.
- [**GitHub.vscode-pull-request-github**](https://marketplace.visualstudio.com/items?itemName=GitHub.vscode-pull-request-github): manage GitHub Pull Requests from VS Code.
- [**Gruntfuggly.todo-tree**](https://marketplace.visualstudio.com/items?itemName=Gruntfuggly.todo-tree): view all TODO, FIXME, and other annotations from a Tab.
- [**IBM.output-colorizer**](https://marketplace.visualstudio.com/items?itemName=IBM.output-colorizer): syntax highlighting for log files.
- [**jebbs.plantuml**](https://marketplace.visualstudio.com/items?itemName=jebbs.plantuml): create UML diagrams to document your project.
- [**mechatroner.rainbow-csv**](https://marketplace.visualstudio.com/items?itemName=mechatroner.rainbow-csv): colorize the columns of CSV files to improve their readability.
- [**mhutchie.git-graph**](https://marketplace.visualstudio.com/items?itemName=mhutchie.git-graph): view and edit your git graph (tags, branches, stashes, …).
- [**mikestead.dotenv**](https://marketplace.visualstudio.com/items?itemName=mikestead.dotenv): syntax highlighting for dotenv files (i.e., contain the environment variables of your program).
- [**ms-vscode.live-server**](https://marketplace.visualstudio.com/items?itemName=ms-vscode.live-server): host a local server for web development.
- [**oderwat.indent-rainbow**](https://marketplace.visualstudio.com/items?itemName=oderwat.indent-rainbow): make code indentation more readable.
- [**pomdtr.excalidraw-editor**](https://marketplace.visualstudio.com/items?itemName=pomdtr.excalidraw-editor): edit Excalidraw diagrams. Great to design architecture diagrams during brainstorm sessions.
- [**sleistner.vscode-fileutils**](https://marketplace.visualstudio.com/items?itemName=sleistner.vscode-fileutils): create, copy, move, rename, and delete files from VS Code commands.
- [**vsls-contrib.gistfs**](https://marketplace.visualstudio.com/items?itemName=vsls-contrib.gistfs): manage and share code snippets on GitHub Gist.
- [**wayou.vscode-todo-highlight**](https://marketplace.visualstudio.com/items?itemName=wayou.vscode-todo-highlight): highlight TODO, FIXME and other keywords in your comments.
- [**wholroyd.jinja**](https://marketplace.visualstudio.com/items?itemName=wholroyd.jinja): language support for Jinja. Popular template language for substituting variables in text files.

#### S Tier: The Super (Optional)

Three features have remarkably enhanced my programming productivity throughout my career: [VIM](https://marketplace.visualstudio.com/items?itemName=vscodevim.vim), [Terminal](https://code.visualstudio.com/docs/terminal/basics), and [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot). **Each of these features contributes to a minimum of a 30% increase in my daily output**. Yet, they may be one of the most difficult VS Code features to master.

#### [Vim](https://marketplace.visualstudio.com/items?itemName=vscodevim.vim) 📝

[If we were living in a simulation, I’m convinced that Vim (and LISP) would be the tools used to program it](https://xkcd.com/224/). Programmers spend a significant portion of their day working with text, and Vim allows you to manipulate text at an astonishing pace. Instead of moving the cursor with a mouse, you can perform high-level operations with just a few keystrokes. For example, “Move the cursor to the next word” is ‘w,’ “delete the current line” is ‘dd,’ or “copy the following line seven times” is ‘yy7p.’ These operations can be combined to create complex commands, such as “Replace all the content between the current parentheses” using ‘ci(‘. The possibilities are virtually limitless, to the extent that there are even [games designed to teach Vim usage](https://vim-adventures.com/)!

![Vim graphical cheat sheet](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/02.webp)

Vim Cheatsheet: [http://www.viemu.com/a_vi_vim_graphical_cheat_sheet_tutorial.html](https://web.archive.org/web/20200108045441/http://www.viemu.com/a_vi_vim_graphical_cheat_sheet_tutorial.html)

Allow me to emphasise the value of Vim with an anecdote. During my master’s degree, I encountered a configuration issue with my Apache HTTP Server and sought help from my teacher, a sysadmin at Peugeot (now Stellantis). He used Vim, and his actions were so rapid that I couldn’t keep up. In a matter of minutes, he had troubleshot my problem. That’s when I made the decision to master Vim and the Linux ecosystem.

The best part is that you can use Vim within VS Code as your primary or secondary keybinding. All it takes is installing the [VSCodeVim](https://marketplace.visualstudio.com/items?itemName=vscodevim.vim) extension and configuring some settings. Keep in mind that mastering Vim requires time, effort, and practice, but if you plan to edit lots of code files in the near future, it’s a valuable investment!

**Bonus: You can use Vim in your Browser with the** [**Vimum**](https://github.com/philc/vimium) **extension.**

- [**vscodevim.vim**](https://marketplace.visualstudio.com/items?itemName=vscodevim.vim): Vim emulation for VS Code, highly recommended!
- [**VSpaceCode.vspacecode**](https://marketplace.visualstudio.com/items?itemName=VSpaceCode.vspacecode): Spacemacs like keybindings (advanced shortcuts relying on Vim leader key).

#### [Terminal](https://code.visualstudio.com/docs/terminal/basics) 👨‍💻

Before switching to VS Code, my tools of choice were [NeoVim](https://neovim.io/) (or [Spacemacs](https://www.spacemacs.org/)), and the terminal served as my IDE. A terminal provides access to an extensive array of tools and commands (cp, tee, awk, grep, find, and more) that can be combined in countless ways. Need to sort and deduplicate all your files? Just use `find . -type f | sort | uniq`. Want to resize a batch of images? You can do it with `find . -type f -name "*.jpg" -exec mogrify -resize 100x100 {} \;`.

**Although the terminal isn’t an extension, it’s a vital feature of VS Code, and its power should not be underestimated**. How many times have I needed to troubleshoot issues or perform advanced tasks that would have required writing complex programs. The terminal’s flexibility is a true asset!

![Command Line Fu: https://xkcd.com/196/](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/03.webp)

Command Line Fu: [https://xkcd.com/196/](https://xkcd.com/196/)

If you’re interested in configuring your terminal, numerous individuals share their “dotfiles” repositories on GitHub. These repositories contain the tools and configurations they use to enhance their command-line interface. You can find mine at this address: [https://github.com/fmind/dotfiles](https://github.com/fmind/dotfiles). Please note that to install them, you’ll need both [Python](https://www.python.org/downloads/) and [Ansible](https://www.ansible.com/).

#### [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) ✈️

[**GitHub Copilot**](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) **is a game changer for programmers**. Once you figure out the program in your head, you have to type it and the time spent between thinking and typing may be 1:10. What if you could just “Tab” your way out? Instead of writing the text yourself, express your intent with clear names or comments, and let GitHub Copilot write the rest for you by pressing “Tab”. This is an autocompletion engine cranked up to 9999, and it is even better now with its new [GitHub Copilot Chat](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat) feature!

![Example of GitHub Copilot in action: https://github.com/features/copilot](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/04.mp4)

Example of GitHub Copilot in action: [https://github.com/features/copilot](https://github.com/features/copilot)

GitHub Copilot proves invaluable in various scenarios: it assists in generating unit tests from code definitions, completes unfamiliar API calls, and creates relevant examples based on your context. It’s intelligent enough to examine your project’s files and adapt to your coding style. This experience is both gratifying and highly productive, and I strongly recommend trying Copilot as soon as possible!

- [**GitHub.copilot**](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot): The smartest autocompletion engine ever!
- [**GitHub.copilot-chat**](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat): don’t ask your colleague, ask Copilot Chat instead :)

### Settings and Keybindings 🤖

Within VS Code, there are two sets of configurations: [Settings](https://code.visualstudio.com/docs/getstarted/settings) that control the application’s behavior and [Keybindings](https://code.visualstudio.com/docs/getstarted/keybindings) that modify your shortcuts. Both can be edited from the “Gear” icon located at the bottom left of VS Code.

#### [Settings](https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-settings-json) 🔧

Below, you’ll find [the link to the settings I utilize with VS Code](https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-settings-json). Each setting is annotated to help you understand what it does. Keep in mind that you can hover your cursor over a setting key in VS Code to access more information about that setting. You can also switch between the textual and visual interface using the “Go to document” icon at the top left of the editor settings.

**Remember that it’s essential to tailor the settings to your preferences since every user is unique**. Additionally, strive to understand what each setting does to optimize your satisfaction and productivity.

![https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-settings-json (163 lines)](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/05.webp)

[https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-settings-json](https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-settings-json) (163 lines)

#### [Keybindings](https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-keybindings-json) 🎹

**Keybindings are primarily a matter of personal preference**. Some individuals may opt for minor modifications, while others may choose to completely rebind commands to their liking.

In my case, I prefer to assign quick shortcuts to the most frequently used commands and utilize the command selection (CTRL+SHIFT+P) for less common commands. To execute these quick shortcuts, I employ a technique I call the “Alt-key trick.” You’re welcome to adopt this approach if you find it beneficial or explore alternatives like [VSpaceCode](https://vspacecode.github.io/) (Spacemacs keybindings for VS Code).

#### The Alt-key Trick 🗡

By default, most desktop applications use the Alt key to navigate through the application menu, allowing actions like “Alt+i i” to access the “Insert” menu and insert an image into a Word document. In VS Code, you can disable this behavior by setting `"window.enableMenuBarMnemonics": false` and create your own custom keybindings. Another advantage is that this behavior works across all major operating systems: Linux, Mac, and Windows.

[The code snippet provided below replaces Alt-key shortcuts with custom keybindings](https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-keybindings-json). For example, pressing “Alt+j” will move to the next editor, and “Alt+,” will open a new terminal. The code snippet is divided into several sections:

1. **ACTIONS**: Primary shortcuts associated with each key on your keyboard.
2. **DISABLED**: Resolving conflicts found in the extensions I’m using.
3. **JUPYTER**: Additional shortcuts for Jupyter.
4. **POPUPS**: Navigating popup menus similar to Vim.
5. **TERMINALS**: Shortcuts related to terminal manipulation.

![https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-keybindings-json (300 lines)](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/06.webp)

[https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-keybindings-json](https://gist.github.com/fmind/67c1ce34d0f21005b4aa7aa79b9162aa#file-keybindings-json) (300 lines)

### Tips and Tricks 👉

#### 1. Synchronization ↔️

Leverage VS Code’s ‘[Settings Sync](https://code.visualstudio.com/docs/editor/settings-sync)’ feature for a seamless development experience across multiple machines. Activate this by clicking the ‘Gear’ icon at the bottom-left of the application to synchronize your configurations, facilitating effortless transitions between different [work profiles](https://code.visualstudio.com/docs/editor/profiles) like Java/Python or personal/professional.

![https://code.visualstudio.com/docs/editor/settings-sync](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/07.webp)

[https://code.visualstudio.com/docs/editor/settings-sync](https://code.visualstudio.com/docs/editor/settings-sync)

#### 2. Command Palette 🎨

Quickly access VS Code’s shortcuts through the [Command Palette](https://code.visualstudio.com/docs/getstarted/userinterface#_command-palette) by using ‘CTRL+SHIFT+P’. Ideal for infrequent commands or when the exact name eludes you. This feature is an essential tool in the VS Code arsenal!

![https://code.visualstudio.com/docs/getstarted/userinterface#\_command-palette](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/08.webp)

[https://code.visualstudio.com/docs/getstarted/userinterface#\_command-palette](https://code.visualstudio.com/docs/getstarted/userinterface#_command-palette)

#### 3. Put the mouse away 🐭

Optimize your coding workflow by mastering keyboard shortcuts; [they surpass the mouse in boosting typing efficiency](https://blog.superhuman.com/keyboard-vs-mouse/). For instance, Vim enthusiasts can adopt the recommended [hand positioning below to enhance performance](https://stackoverflow.com/questions/14021283/position-of-fingers-for-better-productivity-in-vim).

Consider [remapping the Caps Lock key to Ctrl (Windows/Linux) or Cmd (Mac)](https://www.endpointdev.com/blog/2023/04/use-caps-lock-as-escape/) to prevent finger strain.

![https://stackoverflow.com/questions/14021283/position-of-fingers-for-better-productivity-in-vim](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/09.gif)

[https://stackoverflow.com/questions/14021283/position-of-fingers-for-better-productivity-in-vim](https://stackoverflow.com/questions/14021283/position-of-fingers-for-better-productivity-in-vim)

#### 4. Code Workspace File 🗄️

Customize your VS Code environment globally, by folder, or using a workspace. [Workspaces](https://code.visualstudio.com/docs/editor/workspaces) bundle folders for project management, ensuring consistent settings among developers.

Create one via ‘File’ \> ‘Save Workspace As…’ to generate a ‘code-workspace’ file, typically placed at your project’s root.

![VS Code Workspace for the MLOps Python Package project on GitHub](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/10.webp)

VS Code Workspace for the MLOps Python Package project on GitHub

#### 5. Python Interactive Window 🕹️

Transform your Python script into an interactive notebook within VS Code using the [Python Interactive Window](https://code.visualstudio.com/docs/python/jupyter-support-py). Insert ‘# %%’ comments to delineate cells. Edit on the left, execute with ‘Ctrl+Enter’, and view results on the right. You can greatly streamline your coding with this simple integration!

![Python Interactive Window on a simple script](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/11.webp)

Python Interactive Window on a simple script

#### 6. Automation with Make or Invoke 🤖

Automate repetitive commands with a task automation system, directly through VS Code or your shell, to enhance productivity. Consider these three systems:

- [Make](https://www.gnu.org/software/make/): A time-tested tool compatible across all platforms.
- [Invoke](https://www.pyinvoke.org/): Python specific. Great if you want to mix Python code and shell commands. You can improve VS Code integration with [this extension](https://marketplace.visualstudio.com/items?itemName=dchanco.vsc-invoke).
- [VS Code Tasks](https://code.visualstudio.com/docs/editor/tasks): while native to VS Code, I favor Make or Invoke for better collaboration with other developers.

![Example of Invoke tasks in https://github.com/fmind/mlops-python-package](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/12.webp)

Example of Invoke tasks in [https://github.com/fmind/mlops-python-package](https://github.com/fmind/mlops-python-package)

#### 7. Xonsh, Fish, Zsh, PtPython, and others 🐚

Move beyond basic bash with these more advanced shells:

- [Xonsh](https://xon.sh/): merges the familiarity of Python with shell capabilities — a harmonious blend for those preferring Python’s syntax over bash’s complexity.
- [Fish](https://fishshell.com/): offers a superb out-of-the-box experience, though it may not always align with bash standards — a choice for the bash-averse :)
- [Zsh](https://www.zsh.org/): outshines bash in power but requires fine-tuning. Supercharge it with [https://ohmyz.sh/](https://ohmyz.sh/)
- [IPython](https://ipython.org/)/[PtPython](https://github.com/prompt-toolkit/ptpython): not for system shell use, but excellent for an enriched Python interpreter interface.

![Xonsh shell used for executing Python code and Make tasks https://xon.sh/](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/13.webp)

Xonsh shell used for executing Python code and Make tasks [https://xon.sh/](https://xon.sh/)

There are also tons of resources online to further extend your configuration:

- [https://github.com/alebcay/awesome-shell](https://github.com/alebcay/awesome-shell)
- [https://github.com/jorgebucaran/awsm.fish](https://github.com/jorgebucaran/awsm.fish)
- [https://github.com/xonsh/awesome-xontribs](https://github.com/xonsh/awesome-xontribs)
- [https://github.com/agarrharr/awesome-cli-apps](https://github.com/agarrharr/awesome-cli-apps)
- [https://github.com/awesome-lists/awesome-bash](https://github.com/awesome-lists/awesome-bash)
- [https://github.com/unixorn/awesome-zsh-plugins](https://github.com/unixorn/awesome-zsh-plugins)
- [https://github.com/janikvonrotz/awesome-powershell](https://github.com/janikvonrotz/awesome-powershell)

#### 8. Text file can be used for so many things 📄

With proficiency in VS Code, you’ll discover that text-based operations often outperform GUIs in productivity. Activities suited for a text-centric approach include:

- Writing Slides with [Marp for VS Code](https://marketplace.visualstudio.com/items?itemName=marp-team.marp-vscode)
- Creating UML diagrams with [PlantUML](https://marketplace.visualstudio.com/items?itemName=jebbs.plantuml)
- Creating diagrams and charts with [Mermaid](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)
- Managing and tracking your time with [Org Mode](https://marketplace.visualstudio.com/items?itemName=tootone.org-mode)
- Generate graphs and concept maps with [GraphViz](https://graphviz.org/)

![Integration of Mermaid with VS Code https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/14.webp)

Integration of Mermaid with VS Code [https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)

#### 9. Look at other configurations on GitHub 😺

Developers love to publish their settings and keybindings on GitHub, and VS Code is no exception. You can check this [topic](https://github.com/topics/vscode-settings) to track VS Code configurations on GitHub.

I also recommend you subscribe to these sources of tips and tricks:

- [https://vscode.email/](https://vscode.email/) (newsletter)
- [https://twitter.com/code](https://twitter.com/code) (official X account)
- [https://code.visualstudio.com/updates](https://code.visualstudio.com/updates) (official blog)
- [https://www.youtube.com/channel/UCs5Y5_7XK8HLDX0SLNwkd3w](https://www.youtube.com/channel/UCs5Y5_7XK8HLDX0SLNwkd3w) (official YouTube account)

![https://vscode.email/about](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/15.webp)

[https://vscode.email/about](https://vscode.email/about)

#### 10. Use GhostText to use VS Code on the web 👻

When VS Code’s reach seems limited, [GhostText](https://ghosttext.fregante.com/) emerges as an ally. This [Browser](https://chromewebstore.google.com/detail/ghosttext/godiecgffnchndlihlpaajjcplehddca)/[VS Code](https://marketplace.visualstudio.com/items?itemName=fregante.ghost-text) extension enables you to edit browser text areas directly in VS Code. It offers bi-directional sync, allowing edits anywhere, anytime. Disengage sync when your editing is complete.

![https://ghosttext.fregante.com/](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/16.webp)

[https://ghosttext.fregante.com/](https://ghosttext.fregante.com/)

### Conclusions 🌅

**Congratulations on reaching the end of this guide!** Your dedication to refining your development environment is commendable. Remember, the crux of an optimal setup is personalization. Embrace and experiment with your tools’ potential to suit your unique preferences.

Farewell, skilled developer, may your code be efficient and your professional path successful!

![Photo by Taylor Brandon on Unsplash](/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/17.webp)

Photo by [Taylor Brandon](https://unsplash.com/@house_42?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)
