# Installation & Setup Guide

Setting up Ella in your repository is as easy as adding a single GitHub Actions workflow file. You do not need to copy any Python scripts or internal configuration folders!

## Prerequisites

1. You must have access to an LLM endpoint (e.g., OpenAI, Anthropic, or a local self-hosted model) that supports the standard OpenAI Chat Completions API.
2. You need a **GitHub App Private Key** if you want the bot to be able to create PRs, push to Wikis, or edit issues as an App, OR you can simply use the default `${{ secrets.GITHUB_TOKEN }}` if you only need basic comment replies.

## 1. Configure the Workflow

> [!WARNING]
> **This specific action is hardcoded to only obey the `isyuricunha` GitHub user account.** If you want to use it, you **MUST fork** this repository and change the action reference to point to your own fork!

Create a new file in your repository at `.github/workflows/ella.yml` and add the following content:

```yaml
name: Ella Mizuki
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

jobs:
  ella:
    if: >
      (github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'failure' && github.event.workflow_run.name != 'Ella Mizuki') ||
      (github.event_name == 'issue_comment' && contains(github.event.comment.body, '/ella') && github.event.comment.user.login == github.repository_owner) ||
      (github.event_name == 'issues' && github.event.action == 'opened') ||
      (github.event_name == 'pull_request_target' && (github.event.action == 'opened' || github.event.action == 'synchronize'))
    runs-on: ubuntu-latest
    env:
      ELLA_AI_API_KEY: ${{ secrets.ELLA_AI_API_KEY }}
      ELLA_AI_BASE_URL: ${{ secrets.ELLA_AI_BASE_URL }}
      ELLA_AI_MODEL: ${{ secrets.ELLA_AI_MODEL }}
    steps:
      - name: Chamando a Ella
        # REPLACE WITH YOUR GITHUB USERNAME AND FORK NAME
        uses: YOUR_USERNAME/YOUR_FORK_NAME@main
        with:
          ella_app_client_id: ${{ secrets.ELLA_APP_CLIENT_ID }}
          ella_app_private_key: ${{ secrets.ELLA_APP_PRIVATE_KEY }}
```

## 2. Set GitHub Secrets

In your target repository, go to **Settings > Secrets and variables > Actions**, and add the following repository secrets:

- `ELLA_AI_BASE_URL`: The base URL of your LLM API (e.g., `https://api.openai.com/v1`).
- `ELLA_AI_MODEL`: The model name (e.g., `gpt-4o`).
- `ELLA_AI_API_KEY`: Your API key for the LLM.
- `ELLA_APP_CLIENT_ID` & `ELLA_APP_PRIVATE_KEY`: GitHub App credentials.

## 3. Personalize the Agent (Optional)

Ella comes with a core persona already configured. However, if you want to provide repository-specific context or rules, you can create a file named `AGENTS.md` or `ELLA.md` in the root of your target repository. Ella will automatically detect these files and incorporate their instructions!

```markdown
# Repository Instructions
When writing code here, always use strict TypeScript and prefer functional components.
```

## 4. Test the Bot

Create an issue in your repository and use the command `/ella help`. If everything is configured correctly, the workflow will trigger the action, connect to your LLM, and reply!
