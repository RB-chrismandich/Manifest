---
name: pr-manage
description: Unified pull request workflow manager. Dispatches to PR review, monitoring, comment addressing, stack merging, base cleaning, reapply resetting, or bot triaging.
---

# Unified PR Workflow Router

Manage pull request lifecycle actions from a single entry point by dispatching to
specialized PR sub-skills.

## When to use

- Interacting with PRs on GitHub or GitLab when you want natural subcommand routing.
- Performing multi-step PR workflows (reviewing, addressing comments, merging stacked PRs).

## Subcommand Routing

| Subcommand / Intent | Dispatched Skill | Purpose |
|---------------------|------------------|---------|
| `review` | `/manifest-forge:pr-review` | Read-only analysis and disposition recommendation for open PRs |
| `monitor` | `/manifest-forge:pr-monitor` | Track CI/check run progress and review status |
| `address` / `comments` | `/manifest-forge:pr-address-comments` | Systematically address review feedback on the active PR branch |
| `merge` / `merge-stacked` | `/manifest-forge:pr-merge-stacked` | Safely merge stacked PR branches without closing child PRs |
| `clean-base` | `/manifest-forge:pr-clean-base` | Clean up and realign base branches |
| `reset-reapply` | `/manifest-forge:pr-reset-reapply` | Reset tangled branch history and reapply clean net diff |
| `triage-bots` | `/manifest-forge:pr-triage-bots` | Triage and clean machine-generated bot PRs |

## Workflow

1. Parse user intent or subcommand arguments (e.g. `/pr review`, `/pr monitor`, `/pr address`).
2. Dispatch to the target skill, forwarding any flags, PR numbers, or branch filters.
3. If no subcommand is specified, default to `/manifest-forge:pr-review` to summarize open PRs and prompt next action.
