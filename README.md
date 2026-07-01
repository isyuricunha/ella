# Ella Mizuki AI Agent

Ella Mizuki is a powerful, autonomous AI agent that I designed to live inside my GitHub repositories. I built her specifically for myself, to meet my own needs, and to automate tasks exactly the way I like them.

She automatically triages issues, generates multi-page Wiki documentation, reviews pull requests, and manages labels by analyzing the entire codebase.

## ?? Important Notice

- **No Third-Party Support:** I created Ella for my own personal use. I am open-sourcing the code so others can learn from it or adapt it, but **I will not provide support, debugging, or help** for third-party setups. You are on your own!
- **Intellectual Property:** The name "Ella Mizuki", her persona, and her character concept are my intellectual creation. If you fork or copy this project to use in your own repositories, **please rename your bot and create your own persona**. Do not use the name "Ella" or "Ella Mizuki" for your instances.
- **Tailored to My Needs:** The logic here reflects what *I* needed. It might not fit your workflow out of the box.

## How to use (At your own risk)

If you want to adapt my bot for your own projects, you can copy the .ella/ folder into the root of your repository and configure the GitHub Actions workflow.

1. Copy the .ella directory from this repository into your project root.
2. Review and edit the .ella/instructions.md file to create **your own persona, name, and rules**.
3. Copy the example workflow from examples/.github/workflows/ella-mizuki.yml into your project's .github/workflows/ folder (and rename it to match your new bot).
4. Add the necessary secrets to your GitHub repository (e.g., ELLA_AI_API_KEY, ELLA_AI_BASE_URL, ELLA_APP_PRIVATE_KEY).

## Features

- **Issue Triage**: Automatically detects duplicate issues, assigns labels, and replies.
- **Wiki Generation**: Reads the entire codebase and generates a comprehensive, multi-page GitHub Wiki.
- **Pull Request Reviews**: (Coming soon) Analyzes diffs and provides code reviews.
- **Fully Localized**: Runs as a single gent.py script orchestrated entirely by GitHub Actions.

## License

This project is licensed under the **GNU AGPLv3 License**. This ensures that the code remains free and open-source forever. If you modify this code and run it as a service (including as a GitHub Action), you must release your modified source code.
