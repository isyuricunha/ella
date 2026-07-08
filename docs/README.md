# Ella Mizuki - Reference

My personal AI agent integrated via GitHub Actions (`.github/workflows/ella-mizuki.yml`) and driven by `.ella/agent.py`.

## Core Capabilities
- **Triage**: Checks new issues for duplicates, assigns labels, assigns the repo owner (only non-duplicates), and replies. The progress checklist is deleted after completion - only the greeting remains. Skips bot-created issues.
- **Wiki Generation**: Reads the codebase and generates a structured, multi-page GitHub Wiki.
- **Autonomous Coding**: Fixes PRs by committing directly to the branch, or solves issues by creating a branch and opening a PR. Also auto-fixes when a reviewer requests changes.
- **Review**: Reviews code automatically on PR open/synchronize (skips drafts), or on demand via `/ella review`.
- **Plans & Labels**: Writes implementation plans (`/ella plan`) and applies relevant labels (`/ella label`).
- **Q&A**: Answers questions based on issue/PR context (`/ella ask`, `/ella pr`).
- **Issue & PR Management**: Close (`/ella close`), reopen (`/ella reopen`), assign (`/ella assign`), and milestone (`/ella milestone`) issues and PRs.
- **Quote of the Week**: Generates an AI-written quote in a profile README via `workflow_dispatch` or `schedule` events.

## UX Touches
- **Quote replies**: Every bot reply quotes the triggering comment for context.
- **Command suggestions**: Typing a command wrong (e.g., `/ella asl`) suggests the closest match.
- **Reactions**: `eyes` (seen), `+1` (done), `confused` (error/unknown), `-1` (permission denied).
- **Queue feedback**: When a long-running command is queued behind another run, Ella posts a heads-up comment with the wait time.
- **Time remaining**: The progress checklist shows elapsed and remaining time.

## Documentation Index
- [Commands](./commands.md): List of my `/ella` slash commands and automated modes.
- [Internals](./internals.md): My configuration, required secrets, and internal architecture.
- [Setup](./setup.md): How to install Ella in your own repository.

## Quick Trigger
Just tag her in a comment:
```text
/ella solve this bug by replacing X with Y
```
