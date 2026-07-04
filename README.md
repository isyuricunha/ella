<div align="center">
  <h1>🌟 Ella Mizuki AI Agent</h1>
  <p>A powerful, autonomous AI agent that lives directly inside GitHub repositories.</p>

  [![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.10+-yellow.svg)](https://python.org)
  [![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Native-2088FF.svg?logo=github-actions)](https://github.com/features/actions)
</div>

---

> [!NOTE]
> This repository undergoes continuous autonomous auditing and improvement by Ella herself. She reviews her own codebase, fixes bugs, improves documentation, and adds features - all through the same GitHub Actions workflows that power her.

> **Note**: I built Ella specifically for myself, to meet my own needs, and to automate tasks exactly the way I like them.

## Features

### Automated
- **Issue Triage**: Detects duplicate issues, assigns labels, assigns the repo owner (non-duplicates only), and replies. Skips bot-created issues.
- **PR Review**: Analyzes diffs for bugs, security issues, and missing tests. Runs automatically when a PR is opened or synchronized (skips drafts). Also re-triggers automatically when a reviewer requests changes.
- **Auto-Heal**: When a CI workflow fails, downloads the logs, attempts a fix, and commits it to the PR branch.
- **Quote of the Week**: Generates a fresh, AI-written quote in the profile README via `workflow_dispatch` or `schedule` events.

### Slash Commands

**General** (issues and PRs):
- `/ella help` - Lists available commands.
- `/ella ask <question>` - Answers questions based on issue/PR context (no code search).
- `/ella close [reason]` - Closes the current issue or PR with an optional reason.
- `/ella reopen [comment]` - Reopens a closed issue or PR with an optional comment.
- `/ella assign @user` - Assigns a user to the current issue or PR.
- `/ella milestone "name"` - Assigns the issue or PR to a GitHub milestone.
- `/ella label` - Applies the most relevant labels from `.ella/labels.json`.
- `/ella wiki` - Reads the entire codebase and generates a multi-page GitHub Wiki.

**Pull Requests only**:
- `/ella pr <request>` - Short PR analysis (changes, risks, safe to merge).
- `/ella review <request>` - Strict code review with inline comments. Also runs automatically on PR open/synchronize, but skips drafts.
- `/ella fix <request>` - Checks out the branch, applies a fix, and commits directly.
- `/ella continue <request>` - Continues trying to fix if the time/attempt limit was hit.

**Issues only**:
- `/ella plan <request>` - Writes an implementation plan without modifying code.
- `/ella solve <request>` - Creates a new branch, attempts a fix, and opens a new PR.

---

## Getting Started

> [!WARNING]
> **This specific action (`isyuricunha/ella`) is hardcoded to only obey my GitHub user account.** If you want to use it, you **MUST fork** this repository, change the action reference to point to your own fork, **and** update the `isyuricunha` username in the `if:` guard inside `.github/workflows/ella-mizuki.yml` and in the `handle_triage` method of `.ella/agent.py`.

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
  pull_request_review:
    types: [submitted]
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
      (github.event_name == 'pull_request_review' && github.event.review.state == 'changes_requested' && github.event.pull_request.user.login == 'isyuricunha') ||
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

---

## Documentation

For detailed information on how Ella works under the hood, check out the full documentation in the [`/docs`](docs) folder:

- [Setup Guide](docs/setup.md) - Installation, secrets, and configuration.
- [Available Commands](docs/commands.md) - Full list of slash commands and automated modes.
- [Architecture & Internals](docs/internals.md) - Execution flow, model routing, tools, and retry logic.

---

## Important Notice

- **No Third-Party Support:** I created Ella for my own personal use. I am open-sourcing the code so others can learn from it or adapt it, but **I will not provide support, debugging, or help** for third-party setups. You are on your own!
- **Intellectual Property:** The name "Ella Mizuki", her persona, and her character concept are my intellectual creation. If you fork or copy this project to use in your own repositories, **please rename your bot and create your own persona**. Do not use the name "Ella" or "Ella Mizuki" for your instances.
- **Tailored to My Needs:** The logic here reflects what *I* needed. It might not fit your workflow out of the box.
- **Testing:** This project uses pytest. Run `python3 -m pytest tests/ -v` to verify.

## Reporting Issues

When you open an issue on GitHub, you'll be prompted to choose from the following templates:

- **Bug Report** - Something is not working as expected.
- **Feature Request** - Suggest a new idea or improvement.
- **Question** - Ask about how Ella works.

Blank issues are disabled to ensure enough context is provided.

## License

This project is licensed under the **GNU AGPLv3 License**. This ensures that the code remains free and open-source forever. If you modify this code and run it as a service (including as a GitHub Action), you must release your modified source code.

---

**a sentence to brighten your day:**<br>
    every line of code is a step forward
