# Installation & Setup Guide

Setting up Ella in your repository is as easy as adding a single GitHub Actions workflow file. You do not need to copy any Python scripts or internal configuration folders!

## Prerequisites

1. You must have access to an LLM endpoint (e.g., OpenAI, Anthropic, or a local self-hosted model) that supports the standard OpenAI Chat Completions API.
2. You need a **GitHub App Private Key** if you want the bot to be able to create PRs, push to Wikis, or edit issues as an App, OR you can simply use the default `${{ secrets.GITHUB_TOKEN }}` if you only need basic comment replies.

## 1. Configure the Workflow

> [!WARNING]
> **This specific action is hardcoded to only obey the `isyuricunha` GitHub user account.** If you want to use it, you **MUST fork** this repository, change the action reference to point to your own fork, **and** update the `isyuricunha` username in the `if:` guard inside `.github/workflows/ella-mizuki.yml` and in the `handle_triage` method of `.ella/agent.py`. Failing to do so means the bot will ignore all your comments and issues.

Create a new file in your repository at `.github/workflows/ella.yml` and add the following content:

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
      (github.event_name == 'issue_comment' && contains(github.event.comment.body, '/ella') && github.event.comment.user.login == 'YOUR_USERNAME') ||
      (github.event_name == 'issues' && github.event.action == 'opened') ||
      (github.event_name == 'pull_request_target' && (github.event.action == 'opened' || github.event.action == 'synchronize')) ||
      (github.event_name == 'pull_request_review' && github.event.review.state == 'changes_requested' && (github.event.review.user.login == 'YOUR_USERNAME' || github.event.review.user.login == '${{ secrets.ELLA_APP_SLUG }}[bot]')) ||
      github.event_name == 'workflow_dispatch' ||
      github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      - name: Run Ella
        # REPLACE WITH YOUR GITHUB USERNAME AND FORK NAME
        uses: YOUR_USERNAME/YOUR_FORK_NAME@main
        with:
          ella_app_client_id: ${{ secrets.ELLA_APP_CLIENT_ID }}
          ella_app_private_key: ${{ secrets.ELLA_APP_PRIVATE_KEY }}
          ai_base_url: ${{ secrets.ELLA_AI_BASE_URL }}
          ai_model: ${{ secrets.ELLA_AI_MODEL }}
          ai_api_key: ${{ secrets.ELLA_AI_API_KEY }}
          ai_small_model: ${{ secrets.ELLA_AI_SMALL_MODEL }}
          ai_small_api_key: ${{ secrets.ELLA_AI_SMALL_API_KEY }}
          ai_small_base_url: ${{ secrets.ELLA_AI_SMALL_BASE_URL }}
          yuri_commit_name: ${{ secrets.YURI_COMMIT_NAME }}
          yuri_commit_email: ${{ secrets.YURI_COMMIT_EMAIL }}
```

## 2. Set GitHub Secrets

In your target repository, go to **Settings > Secrets and variables > Actions**, and add the following repository secrets:

- `ELLA_AI_BASE_URL`: The base URL of your LLM API (e.g., `https://api.openai.com/v1`).
- `ELLA_AI_MODEL`: The model name for coding tasks and reviews (e.g., `gpt-4o`).
- `ELLA_AI_API_KEY`: Your API key for the LLM.
- `ELLA_APP_CLIENT_ID` & `ELLA_APP_PRIVATE_KEY`: GitHub App credentials.
- `YURI_COMMIT_NAME` & `YURI_COMMIT_EMAIL`: Git author name and email for commit metadata.

**Optional - Small Model** (for triage, ask, pr, plan, label, wiki, quote):
- `ELLA_AI_SMALL_MODEL`: Smaller model name (e.g., `gpt-4o-mini`). Defaults to `ELLA_AI_MODEL` if not set.
- `ELLA_AI_SMALL_API_KEY`: API key for the small model. Defaults to `ELLA_AI_API_KEY`.
- `ELLA_AI_SMALL_BASE_URL`: Base URL for the small model. Defaults to `ELLA_AI_BASE_URL`.

**Optional - Token Limits** (override defaults for specific modes):
- `ELLA_MAX_TOKENS_ASK` (default 4096), `ELLA_MAX_TOKENS_PR` (16384), `ELLA_MAX_TOKENS_REVIEW` (16384), `ELLA_MAX_TOKENS_PLAN` (16384), `ELLA_MAX_TOKENS_LABEL` (4096), `ELLA_MAX_TOKENS_FIX` (16384), `ELLA_MAX_TOKENS_CONTINUE` (16384), `ELLA_MAX_TOKENS_SOLVE` (16384), `ELLA_MAX_TOKENS_HEAL` (16384), `ELLA_MAX_TOKENS_TRIAGE` (16384), `ELLA_MAX_TOKENS_QUOTE` (4096), `ELLA_MAX_TOKENS_WIKI` (16384).
- `ELLA_MAX_ATTEMPTS`: Max loops for fixes (default 25 + 2 per allowed file, capped 300).
- `ELLA_TIME_LIMIT_SECONDS`: Max execution time (default 3600s).
- `ELLA_CMD_RETRIES`: Max retries for transient gh/git/AI failures (default 3, exponential backoff).
- `ELLA_MAX_CONTEXT_PR_DIFF_BYTES` (500000), `ELLA_MAX_CONTEXT_FILE_BYTES` (120000), `ELLA_MAX_CONTEXT_REQUESTED_FILE_BYTES` (250000), `ELLA_MAX_CONTEXT_REPO_FILES_BYTES` (200000).

> [!NOTE]
> `ELLA_MAX_ATTEMPTS`, `ELLA_TIME_LIMIT_SECONDS`, and `ELLA_CMD_RETRIES` can be passed as action `with:` inputs (`ella_max_attempts`, `ella_time_limit_seconds`, `ella_cmd_retries`). Token and context limits (`ELLA_MAX_TOKENS_*`, `ELLA_MAX_CONTEXT_*`) are not action inputs - set them as `env:` on the calling workflow job and they will be inherited by the composite action's `run` step.

**Note on reasoning models**: If your LLM is a reasoning model (e.g., DeepSeek-R1, GLM with thinking), it spends tokens on internal reasoning before generating content. The defaults above are tuned for reasoning models. If you use a non-reasoning model, you can lower these limits to save costs.

## 3. Personalize the Agent (Optional)

Ella comes with a core persona already configured. However, if you want to provide repository-specific context or rules, you can create any of these files in the root of your target repository (checked in order): `AGENTS.md`, `ELLA.md`, `.github/copilot-instructions.md`, or `.github/ella-instructions.md`. Ella will automatically detect these files and incorporate their instructions!

```markdown
# Repository Instructions
When writing code here, always use strict TypeScript and prefer functional components.
```

## 4. Test the Bot

Create an issue in your repository, then comment `/ella help` on it. If everything is configured correctly, the workflow will trigger the action, connect to your LLM, and reply!
