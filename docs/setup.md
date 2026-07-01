# Installation & Setup Guide

Since this agent was built specifically for my workflow, setting it up in your own repository requires you to manually copy and edit a few files.

## Prerequisites

1. You must have access to an LLM endpoint (e.g., NVIDIA NIM, OpenAI, or a local self-hosted model) that supports the standard OpenAI Chat Completions API.
2. You need a **GitHub App Private Key** if you want the bot to be able to create PRs, push to Wikis, or edit issues as an App, OR you can simply use the default `${{ secrets.GITHUB_TOKEN }}` if you only need basic comment replies.

## 1. Copy the Files

Copy the entire `.ella` directory from this repository into the root of your own repository.

```bash
cp -r /path/to/ella/.ella /path/to/your/repo/.ella
```

## 2. Personalize the Agent

Open `.ella/instructions.md` and rewrite the instructions.
**Do not use the name Ella Mizuki**. Create your own persona!

```markdown
# Instructions
You are [YOUR BOT NAME], an AI assistant for [YOUR REPO].
...
```

## 3. Configure the Workflow

Copy the example GitHub Actions workflow into your project:

```bash
mkdir -p .github/workflows
cp /path/to/ella/examples/.github/workflows/ella-mizuki.yml .github/workflows/ai-agent.yml
```

Edit `.github/workflows/ai-agent.yml` to match your new bot's name and ensure it triggers correctly.

## 4. Set GitHub Secrets

In your target repository, go to **Settings > Secrets and variables > Actions**, and add the following repository secrets:

- `ELLA_AI_BASE_URL`: The base URL of your LLM API (e.g., `https://integrate.api.nvidia.com/v1`).
- `ELLA_AI_MODEL`: The model name (e.g., `nvidia/nemotron-3-ultra-550b-a55b`).
- `ELLA_AI_API_KEY`: Your API key for the LLM.
- `ELLA_APP_CLIENT_ID` & `ELLA_APP_PRIVATE_KEY`: If using a GitHub App for authentication.

*(You should also rename these environment variables in `agent.py` and your workflow to match your new bot's name).*

## 5. Test the Bot

Create an issue in your repository and tag your new bot, or include the trigger command (e.g., `/agent`). If everything is configured correctly, the workflow will run `python3 .ella/agent.py` and reply!
