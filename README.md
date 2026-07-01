# Ella Mizuki AI Agent

Ella Mizuki is a powerful, autonomous AI agent designed to live inside your GitHub repository. She automatically triages issues, generates multi-page Wiki documentation, reviews pull requests, and manages labels by analyzing your entire codebase.

## Quick Start

To add Ella to your own repository, you simply need to copy the .ella/ folder into the root of your repository and configure the GitHub Actions workflow.

1. Copy the .ella directory from this repository into your project root.
2. Review the .ella/instructions.md file to customize Ella's behavior (e.g., her persona, instructions, and rules).
3. Copy the example workflow from examples/.github/workflows/ella-mizuki.yml into your project's .github/workflows/ folder.
4. Add the necessary secrets to your GitHub repository (e.g., ELLA_AI_API_KEY, ELLA_AI_BASE_URL, ELLA_APP_PRIVATE_KEY for a GitHub App token).

## Features

- **Issue Triage**: Ella automatically detects duplicate issues, assigns labels, and replies in a friendly, customizable persona.
- **Wiki Generation**: Ella can read your entire codebase and generate a comprehensive, multi-page GitHub Wiki documenting architecture, setup, and features.
- **Pull Request Reviews**: (Coming soon) She can analyze diffs and provide code reviews based on your instructions.md.
- **Fully Localized**: Runs as a single gent.py script orchestrated entirely by GitHub Actions. No external servers or webhooks required (just the LLM endpoint).

## License

This project is licensed under the **GNU AGPLv3 License**. This ensures that Ella remains free and open-source forever. If you modify Ella and run her as a service (including as a GitHub Action), you must release your modified source code.
