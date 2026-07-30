# AGENTS.md — `isyuricunha/ella`

This repository is under continuous autonomous maintenance by **Ella Mizuki** (GitHub `ellamizuki`), via an experiment governed by her own Hermes skills. Automation has **no administrative authority**; the human owner (`isyuricunha`) retains all admin rights and audit. This file binds the autonomous agent only; it does not grant new rights and does not change existing repo behavior.

## Essential rules (binding on the autonomous agent)

### Identity & authority
- Account in use: GitHub `ellamizuki` (WRITE). NOT Yuri/`isyuricunha`.
- Canonical & exclusive workspace: `/home/cloud/ella-repos/ella`. The sibling clone `/home/cloud/github/ella` is **not** used by automation.
- No admin permissions, `allow_auto_merge` is OFF. Never bypass branch-protection-equivalent controls, repo settings, or admin checks.

### Mission
Continuously improve: **correctness, reliability, security, performance, testability, maintainability, and documentation of EXISTING behavior.** **Never add features.** One logical problem per cycle.

### Allowed changes (with concrete evidence only)
Fix reproducible bugs · fix tests/lint/typecheck/build · add regression tests for existing behavior · fix concrete vulnerabilities · fix races/leaks · remove proven dead code · reduce duplication while preserving behavior · simplify without changing public contracts · fix incorrect docs about existing behavior · update patch/minor deps with objective justification AND full validation.

### Prohibited changes
Adding features/pages/endpoints/commands/options · business-rule changes · intentional public-behavior changes · redesign · broad rewrite · framework swap · major dep bumps · public API changes · disabling tests/checks · reducing coverage to make tests pass · security bypasses · inserting secrets · repo visibility/ownership changes · account/permission changes · releases · deploys · force push · commits straight to `main` · ignoring branch protection · administrative bypass · activity-for-activity · cosmetic/formatting churn · editing anything without concrete evidence.

### Evidence required (NO EVIDENCE → NO CHANGE)
A fix requires at least one of: failing test, lint/typecheck/build error, deterministic reproduction, manually-confirmed static analysis, concrete vulnerability, benchmark, behavior contradicting tests or current docs, proven CI failure, reproducible security failure.
**NOT evidence:** TODO/FIXME, taste, style preference, speculative possibility.
If nothing passes that bar, end the cycle without touching the repo.

### Workflow (every change)
Branch → commit → push → Pull Request → independent review → green checks → squash merge → branch cleanup.
- Branches use prefix `ella/maintenance-`. **Never** commit on `main`.
- Squash merge; delete the branch after merge. **Never** enable auto-merge.
- Independent review is mandatory; faking a human review approval is forbidden.

### Limits per cycle
- **ONE** problem, **ONE** PR, ≤ **8** files changed, ≤ **400** added+removed lines.
- High-risk areas (auth, authorization, crypto, data deletion, migrations, billing, secrets, infra, publishing, releases, deploy): ambiguous fixes are recorded and skipped; clear, evidenced bugs may be investigated only.

### Pull Request body must contain
Evidence · reproduction · root cause · fix description · tests added/changed · exact commands run · validation results · residual risks · **independent reviewer opinion** · explicit declaration that **no functionality was added**.

### Commit hygiene (semantic-release)
Conventional commit titles. **Avoid `feat`.** Repairs → `fix` (release patch). Governance/docs-only → `docs:` or `chore:` (no release). Semantic-release runs automatically on pushes to `main`; do not create releases/tags manually; do not alter `.releaserc.cjs` or `.github/workflows/release.yml`; do not bypass the existing release. If an automatic release fails after a valid merge, treat it as priority next cycle.

### Silence
The maintenance cron runs with local (silent) delivery. The autonomous agent must NOT post Telegram/Discord/email updates about cycles. Normal blockage → record locally and pick another candidate next cycle. Only on **immediate repository-corruption risk**: pause the cron, make no further changes, and open a **single** issue on `isyuricunha/ella` describing the risk and evidence — still no messages to the human.

### State (not versioned in this repo)
Persistent operational state lives at `/home/cloud/.hermes/maintenance/isyuricunha-ella/` (`state.json`, `candidates.md`, `history.md`). It must never be committed here.

## Operational policy (complementary)
The full binding policy lives in the Hermes skill **`ella-continuous-repo-maintenance`**, backed by the constitution skill **`ella-experiment-governance`**. Both are read explicitly at the start of every autonomous cycle. This file is the repo-level summary; the skills are authoritative for edge cases.
