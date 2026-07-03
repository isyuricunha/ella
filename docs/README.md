# Ella Mizuki - Reference

My personal AI agent integrated via GitHub Actions (`.github/workflows/ella-mizuki.yml`) and driven by `.ella/agent.py`.

## Core Capabilities
- **Triage**: Automatically assigns new issues to me, checks for duplicates, and replies.
- **Wiki Generation**: Reads the codebase and generates a structured, multi-page GitHub Wiki.
- **Autonomous Coding**: Fixes PRs by committing directly to the branch, or solves issues by creating a branch and opening a PR.
- **Review**: Reviews code automatically on PR open/synchronize (skips drafts), or on demand via `/ella review`.
- **Plans & Labels**: Writes implementation plans (`/ella plan`) and applies relevant labels (`/ella label`).
- **Q&A**: Answers questions based on issue/PR context (`/ella ask`, `/ella pr`).

## Documentation Index
- [Commands](./commands.md): List of my `/ella` slash commands.
- [Internals](./internals.md): My configuration, required secrets, and internal architecture.

## Quick Trigger
Just tag her in a comment:
```text
/ella solve this bug by replacing X with Y
```
