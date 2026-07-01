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

- 🕵️‍♀️ **Issue Triage**: Automatically detects duplicate issues, assigns labels, and replies.
- 📚 **Wiki Generation**: Reads the entire codebase and generates a comprehensive, multi-page GitHub Wiki.
- 💻 **Pull Request Reviews**: (Coming soon) Analyzes diffs and provides code reviews.
- ⚡ **Fully Localized**: Runs as a single `agent.py` script orchestrated entirely by GitHub Actions.

## ⚠️ Important Notice

- **No Third-Party Support:** I created Ella for my own personal use. I am open-sourcing the code so others can learn from it or adapt it, but **I will not provide support, debugging, or help** for third-party setups. You are on your own!
- **Intellectual Property:** The name "Ella Mizuki", her persona, and her character concept are my intellectual creation. If you fork or copy this project to use in your own repositories, **please rename your bot and create your own persona**. Do not use the name "Ella" or "Ella Mizuki" for your instances.
- **Tailored to My Needs:** The logic here reflects what *I* needed. It might not fit your workflow out of the box.

## 🚀 How to use (At your own risk)

If you want to adapt my bot for your own projects, you can copy the `.ella/` folder into the root of your repository and configure the GitHub Actions workflow.

1. Copy the `.ella` directory from this repository into your project root.
2. Review and edit the `.ella/instructions.md` file to create **your own persona, name, and rules**.
3. Copy the example workflow from `examples/.github/workflows/ella-mizuki.yml` into your project's `.github/workflows/` folder (and rename it to match your new bot).
4. Add the necessary secrets to your GitHub repository (e.g., `ELLA_AI_API_KEY`, `ELLA_AI_BASE_URL`, `ELLA_APP_PRIVATE_KEY`).

## 📖 Documentation

For detailed information on how Ella works under the hood, check out the full documentation in the `/docs` folder:

- [Setup Guide](docs/setup.md)
- [Available Commands](docs/commands.md)
- [Architecture & Internals](docs/internals.md)

## 📝 License

This project is licensed under the **GNU AGPLv3 License**. This ensures that the code remains free and open-source forever. If you modify this code and run it as a service (including as a GitHub Action), you must release your modified source code.
