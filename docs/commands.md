# Ella Commands

Slash commands I can use to trigger Ella. For security, she only responds to my GitHub account (`isyuricunha`).

### General (issues and PRs)
- `/ella help`: Lists available commands.
- `/ella ask <question>`: Answers questions based on the issue/PR text in context. Does not search the codebase - if the answer isn't in the issue or PR description, says so.
- `/ella wiki`: Reads the entire codebase and generates a comprehensive, multi-page GitHub Wiki.
- `/ella label`: Applies the most relevant labels defined in `.ella/labels.json`.
- `/ella close [reason]`: Closes the current issue or PR. `reason` can be `completed`, `not_planned`, `duplicate`, or any text (defaults to `not_planned`). Free text is posted as a closing comment.
- `/ella reopen [comment]`: Reopens a closed issue or PR with an optional comment.
- `/ella assign @user`: Assigns a user to the current issue or PR.
- `/ella milestone "name"`: Adds the issue or PR to a GitHub milestone by name (case-insensitive).

### Pull Requests
*(Only work in PR comments)*
- `/ella pr <request>`: Short PR analysis (changes, risks, safe to merge).
- `/ella review <request>`: Strict code review (bugs, security, missing tests). Also runs automatically when a PR is opened or synchronized, but skips draft PRs.
- `/ella fix <request>`: Checks out the branch, applies a fix, and commits directly.
- `/ella continue <request>`: Continues trying to fix if the time/attempt limit was hit.

### Issues
*(Only work in Issue comments)*
- `/ella plan <request>`: Writes an implementation plan without modifying code.
- `/ella solve <request>`: Creates a new branch, attempts a fix, and opens a new PR.

### Automated
- **Triage**: Runs automatically when any issue is opened. Checks for duplicate issues, assigns labels, assigns the repo owner if the issue is not a duplicate, and leaves a welcome message. Skips issues created by bots.
- **Auto-Review**: Runs automatically when a PR is opened or synchronized. Performs a thorough code review and posts inline comments. Skips draft PRs.
- **Auto-Fix on Changes Requested**: When a reviewer submits `changes_requested` on a PR, Ella automatically attempts to fix the review feedback via the same `fix` loop. Triggered by the `pull_request_review` event (type `submitted`). Only fires for PRs created by the repo owner.
- **Auto-Heal**: Runs automatically when a CI workflow fails. Analyzes the logs, attempts to fix the issue, and commits the fix to the PR branch.
- **Quote of the week**: Triggered by a `workflow_dispatch` or `schedule` GitHub Action. Generates a short uplifting sentence, rewrites the quote line in the repo's `README.md`, and commits. Not a slash command - triggered by event type. On this repo, the `schedule` trigger is documented in a comment above the `on:` block in `.github/workflows/ella-mizuki.yml`; add it to enable weekly auto-generation.
