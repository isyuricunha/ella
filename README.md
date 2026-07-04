<div align="center">
  <h1>🌟 Ella Mizuki AI Agent</h1>
  <p>A powerful, autonomous AI agent that lives directly inside GitHub repositories.</p>

  [![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.10+-yellow.svg)](https://python.org)
  [![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Native-2088FF.svg?logo=github-actions)](https://github.com/features/actions)
</div>

---

> **Note**: I built Ella specifically for myself, to meet my own needs, and to automate tasks exactly the way I like them.

## ✨ Features

- 🕵️‍♀️ **Issue Triage**: Automatically detects duplicate issues, assigns labels, assigns the repo owner (only for non-duplicates), and replies. Skips bot-created issues.
- 💻 **Pull Request Reviews**: Analyzes diffs for bugs, security issues, and missing tests. Runs automatically when a PR is opened or synchronized (skips drafts), or on demand via `/ella review`.
- 🔧 **Autonomous Fixes**: Fixes PRs by committing directly to the branch (`/ella fix`), or solves issues by creating a branch and opening a PR (`/ella solve`).
- 📋 **Plans & Labels**: Writes implementation plans (`/ella plan`) and applies relevant labels (`/ella label`).
- 💬 **Q&A**: Answers questions based on issue/PR context (`/ella ask`, `/ella pr`).
- 📚 **Wiki Generation**: Reads the entire codebase and generates a comprehensive, multi-page GitHub Wiki.
- 📝 **Quote of the Week**: Generates a fresh, AI-written quote in a profile README via `workflow_dispatch` or `schedule` events. Not a slash command - triggered by event type.
- ⚡ **Fully Localized**: Runs as a single `agent.py` script orchestrated entirely by GitHub Actions.

## ⚠️ Important Notice

- **No Third-Party Support:** I created Ella for my own personal use. I am open-sourcing the code so others can learn from it or adapt it, but **I will not provide support, debugging, or help** for third-party setups. You are on your own!
- **Intellectual Property:** The name "Ella Mizuki", her persona, and her character concept are my intellectual creation. If you fork or copy this project to use in your own repositories, **please rename your bot and create your own persona**. Do not use the name "Ella" or "Ella Mizuki" for your instances.
- **Tailored to My Needs:** The logic here reflects what *I* needed. It might not fit your workflow out of the box.
- **Testing:** This project uses pytest. Run `python3 -m pytest tests/ -v` to verify.

## 🚀 How to use (At your own risk)

> [!WARNING]
> **This specific action (`isyuricunha/ella`) is hardcoded to only obey my GitHub user account.** If you want to use it, you **MUST fork** this repository and change the action reference to point to your own fork!

If you want to use Ella in your own projects, you can use her as a **GitHub Action**. You do not need to copy any script files to your repository.

1. **Fork** this repository to your own account.
2. Create a workflow file in your target repository, e.g., `.github/workflows/ella.yml`.
3. Use your fork's action and pass your credentials:

```yaml
name: Ella Mizuki
# To enable weekly quote generation, add a schedule trigger to the on: block:
#   schedule:
#     - cron: "0 0 * * 0"
on:
  issues:
    types: [opened]
  issue_comment:
    types: [created]
  pull_request_target:
    types: [opened, synchronize]
  workflow_run:
    workflows: ["*"]
    types: [completed]
  workflow_dispatch:

jobs:
  ella:
    if: >
      (github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'failure' && github.event.workflow_run.name != 'Ella Mizuki' && github.event.workflow_run.name != 'Release') ||
      (github.event_name == 'issue_comment' && contains(github.event.comment.body, '/ella') && github.event.comment.user.login == 'isyuricunha') ||
      (github.event_name == 'issues' && github.event.action == 'opened') ||
      (github.event_name == 'pull_request_target' && (github.event.action == 'opened' || github.event.action == 'synchronize')) ||
      github.event_name == 'workflow_dispatch' ||
      github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      # REPLACE WITH YOUR GITHUB USERNAME AND FORK NAME
      - uses: YOUR_USERNAME/YOUR_FORK_NAME@main
        with:
          ella_app_client_id: ${{ secrets.ELLA_APP_CLIENT_ID }}
          ella_app_private_key: ${{ secrets.ELLA_APP_PRIVATE_KEY }}
```

4. **(Optional)** To customize her persona for your specific repository, create an `ELLA.md`, `AGENTS.md`, `.github/copilot-instructions.md`, or `.github/ella-instructions.md` file in the root of your repository with your extra instructions.

## 📖 Documentation

For detailed information on how Ella works under the hood, check out the full documentation in the `/docs` folder:

- [Setup Guide](docs/setup.md)
- [Available Commands](docs/commands.md)
- [Architecture & Internals](docs/internals.md)

## 🐛 Reporting Issues

When you open an issue on GitHub, you'll be prompted to choose from the following templates:

- **Bug Report** - Something is not working as expected
- **Feature Request** - Suggest a new idea or improvement
- **Question** - Ask about how Ella works

Blank issues are disabled to ensure enough context is provided.

## 📝 License

This project is licensed under the **GNU AGPLv3 License**. This ensures that the code remains free and open-source forever. If you modify this code and run it as a service (including as a GitHub Action), you must release your modified source code.

**a sentence to brighten your day:**<br>
    every line of code is a step forward

