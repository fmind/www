+++
title = "Taming Python Installation with Pyenv for AI/ML and MLOps Projects"
description = "Tame your Python chaos! Learn how pyenv simplifies managing Python versions for AI/ML \u0026 MLOps, ensuring smooth, reproducible development."
date = "2024-10-08"
tags = ["Python", "Guide"]
slug = "taming-python-installation-with-pyenv-for-ai-ml-and-mlops-projects"
syndicated = "https://medium.com/@fmind/taming-python-installation-with-pyenv-for-ai-ml-and-mlops-projects-00cb0bec09b4"
draft = false
+++

[Python](https://www.python.org/) is the beloved language of data scientists, machine learning engineers, and anyone dabbling in the fascinating world of AI. But with its ever-evolving landscape of versions and dependencies, managing your Python environment can quickly turn into a chaotic nightmare. Fear not, fellow data wizards! This blog post introduces you to [**pyenv**](https://github.com/pyenv/pyenv), your secret weapon for taming the Python beast and ensuring a smooth, reproducible, and headache-free development experience.

![https://m.xkcd.com/1987/](/static/img/articles/taming-python-installation-with-pyenv-for-ai-ml-and-mlops-projects/cover.webp)

[https://m.xkcd.com/1987/](https://m.xkcd.com/1987/)

### The Python Version Problem

AI/ML practitioners are juggling between multiple projects. One requires [Python 3.9](https://www.python.org/downloads/release/python-390/) for compatibility with a crucial library, while another demands the shiny new features of Python [3.13](https://docs.python.org/3.13/whatsnew/3.13.html). Switching between these versions manually can be a recipe for disaster, leading to broken dependencies and frustrating debugging sessions. System-wide Python installations become a minefield, and [virtual environments](https://docs.python.org/3/library/venv.html), while helpful, can still be cumbersome to manage across multiple projects.

### Enter Pyenv: The Python Version Manager

[pyenv](https://github.com/pyenv/pyenv) is a lightweight command-line tool that allows you to effortlessly install and switch between multiple Python versions on your system. It acts as a gatekeeper, intercepting Python commands and directing them to the appropriate version based on your project’s needs. This means you can have Python 3.11, 3.12, 3.13, and other versions coexisting peacefully, each neatly tucked away in its own isolated environment.

### Why Choose Pyenv?

- **Simplicity:** pyenv’s command-line interface is clean and intuitive, making it easy to learn and use.
- **Flexibility:** Install and manage any Python version, from legacy releases to the latest cutting-edge builds.
- **Project-Specific Versions:** Specify the exact Python version for each project, ensuring consistent and reproducible results.
- **No Root Privileges Required:** Install Python versions locally without needing administrator access, perfect for shared systems or environments where you don’t have root privileges.
- **Lightweight and Fast:** pyenv’s minimal footprint ensures it doesn’t bog down your system, providing quick and efficient version switching.

### Choosing the Right Python Version

For new AI/ML and MLOps projects, embracing the latest stable Python release is generally recommended. Newer versions often bring performance enhancements, bug fixes, and exciting new features that can boost your productivity. However, compatibility with existing libraries and frameworks is paramount. **Always check the requirements of your production environment before upgrading to ensure a smooth transition**. The official Python website provides [a list of supported versions](https://www.python.org/downloads/), and it’s wise to steer clear of unsupported releases to avoid security vulnerabilities and compatibility issues.

### Installing Pyenv

The installation process is straightforward, varying slightly depending on your operating system. The comprehensive instructions on the official [pyenv](https://github.com/pyenv/pyenv) GitHub repository ([https://github.com/pyenv/pyenv#installation](https://www.google.com/url?sa=E&q=https%3A%2F%2Fgithub.com%2Fpyenv%2Fpyenv%23installation)) provide detailed guidance for different platforms.

#### Getting Pyenv

For macOS, UNIX and Windows+[WSL](https://learn.microsoft.com/en-us/windows/wsl/install) systems, use the automatic installer:

```bash
curl https://pyenv.run | bash
```

#### Setting Up Your Shell Environment

For bash and zsh shells, add these lines to both ~/.bashrc and ~/.zshrc or ~/.profile:

```bash
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```

#### Restart Your Shell

Finally, restart your shell to update your shell PATH:

```bash
exec "$SHELL"
```

**Important: Be sure** [**to install Python build dependencies**](https://github.com/pyenv/pyenv/wiki#suggested-build-environment) **on your system after the installation.**

### Using Pyenv

Once installed, using pyenv is a breeze:

- **Install a Python Version:**

&nbsp;

```bash
pyenv install 3.12.0
```

- **Set a Global Version (Optional):**

&nbsp;

```bash
pyenv global 3.12.0
```

- **Set a Local Version (Project-Specific):** Create a .python-version file in your project’s root directory containing the desired version (e.g., 3.12.0). pyenv automatically switches to this version when you enter the project directory.

&nbsp;

```text
# in .python-version
3.12
```

- **Check Active Version:**

&nbsp;

```bash
pyenv version
```

### Example Workflow

Let’s say you’re starting a new project that requires Python 3.12:

```bash
mkdir my-mlops-project
cd my-mlops-project
pyenv install 3.12
echo "3.12" > .python-version
python --version  # Verify the correct version is active
```

Now, whenever you work within the my-mlops-project directory, pyenv ensures you’re using the correct Python version.

### Conclusion

[pyenv](https://github.com/pyenv/pyenv) is an indispensable tool for any data scientist or MLOps engineer working with Python. It simplifies version management, promotes project isolation, and ensures reproducibility, allowing you to focus on what you do best: crafting innovative AI/ML solutions. So, ditch the Python version headaches and embrace the power of pyenv! Your future self will thank you.

_To learn more about best practices for MLOps Coding, check this course:_ [_https://mlops-coding-course.fmind.dev/_](https://mlops-coding-course.fmind.dev/)

![Take care of your Python environment. Photo by Karsten Würth on Unsplash](/static/img/articles/taming-python-installation-with-pyenv-for-ai-ml-and-mlops-projects/02.webp)

Take care of your Python environment. Photo by [Karsten Würth](https://unsplash.com/@karsten_wuerth?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)
