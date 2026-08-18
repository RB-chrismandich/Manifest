---
name: issue-manage
description: Unified issue management manager. Dispatches to issue triage, prioritization, specification preparation, automated development, and git/PR synchronization.
---

# Unified Issue Workflow Router

Manage issues across issue trackers (Linear, GitHub, GitLab, Jira) through a single
router interface.

## When to use

- Triaging, ranking, preparing, developing, or syncing issues with commits and PRs.
- Moving an issue through its complete lifecycle from backlog to merged implementation.

## Subcommand Routing

| Subcommand / Intent | Dispatched Skill | Purpose |
|---------------------|------------------|---------|
| `triage` | `/manifest-forge:issue-triage` | Backlog audit: duplicate detection, staleness, priority validation |
| `prioritize` | `/manifest-forge:issue-prioritize` | Multi-factor scoring (impact, urgency, readiness, risk) |
| `prep` / `spec` | `/manifest-forge:issue-prep-auto` | Transform raw issue into structured technical specification |
| `dev` / `implement` | `/manifest-forge:issue-dev-auto` | Drive spec-gated development cycle for an issue |
| `sync-commit` | `/manifest-forge:issue-sync-commit` | Link local commits and transition issue state |
| `sync-pr` | `/manifest-forge:issue-sync-pr` | Synchronize PR description, metadata, and status with issue |

## Workflow

1. Parse the command argument or intent (e.g. `/issue triage`, `/issue prioritize`, `/issue dev <KEY>`).
2. Dispatch to the specialized issue skill with tracker context.
3. If no subcommand is given, default to `/manifest-forge:issue-prioritize` to recommend top actionable issues.
