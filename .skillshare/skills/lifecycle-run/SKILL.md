---
name: lifecycle-run
description: Drive a feature/issue through the codified state-gated lifecycle (specify→…→verify) with hard phase-gating and a smoke-test Verify gate; entry is a ticket URL/issue key.
---

# Lifecycle Orchestrator

Thin front-end over `configs/claude/scripts/lifecycle.sh` (the shared, bats-tested state
machine). The script holds the gate logic and per-track state; this skill maps each phase to
the command that executes it, runs it, then calls `lifecycle.sh advance` with the phase's
gate signal. Constitution: Principle VI + "Development Lifecycle". Contracts:
`specs/365-lifecycle-codification/contracts/`.

## Phase → command map

| # | Phase | Command(s) | Gate (exit criterion) |
|---|-------|-----------|-----------------------|
| 1 | specify | `/speckit-specify` | artifact: `spec.md` exists |
| 2 | clarify | `/speckit-clarify` | artifact: clarifications resolved |
| 3 | spec_review_product | `/spec-review --mode product` | verdict: APPROVED |
| 4 | plan | `/speckit-plan` | artifact: `plan.md` + design |
| 5 | task_creation | `/speckit-tasks` + `/speckit-taskstoissues` | artifact: `tasks.md` + hierarchy provisioned |
| 6 | analyze | `/speckit-analyze` | verdict: 0 critical |
| 7 | spec_review_tech | `/spec-review --mode technical` | verdict: APPROVED |
| 8 | implement | `/speckit-implement` | coverage: every shipped user-facing workflow has a smoke test (or exempt) |
| 9 | verify | `/spec-audit-tasks` + `smoke_test.py run --tier Lite` | runner: exit 0 |

> The `--mode product|technical` flag routes the state dir and selects the
> matching template (`prompts/spec_review.md` vs `prompts/spec_review_technical.md`).

## Usage

```bash
# Start a track from a ticket URL / issue key
lifecycle.sh init PROJ-123              # or org/repo#42, a Linear/GitLab URL, etc.
lifecycle.sh status PROJ-123 --json     # where am I, what's outstanding

# For the current phase: run its command, then advance with the gate signal
lifecycle.sh advance <track-id> --actor <agent|human> --gate '<phase-gate-json>'
#   artifact:  {"gate_type":"artifact","present":true}
#   verdict:   {"gate_type":"verdict","verdict":"APPROVED|NEEDS_REVIEW|BLOCKED"}
#   coverage:  {"gate_type":"coverage","coverage":"OK|MISSING"}
#   runner:    {"gate_type":"runner","exit_code":0}
```

## Gating semantics

- **Agents** (`--actor agent`): a skip or a failing gate is **refused** (exit 1) — halt and
  flag `needs-human`. Never advance/merge past a failing gate.
- **Humans** (`--actor human`): a skip or failing gate is an **advisory warning** (exit 3);
  proceed only with `--override "<reason>"`, which is logged.
- **Verify**: backed by the smoke orchestrator (run from the project root —
  the catalog root defaults to the relative `./smoke-catalog`; pass
  `--catalog-dir` when invoking from elsewhere). Missing coverage (`smoke_test.py run` exit 2,
  EMPTY) is a failure — never a pass. Non-user-facing Sub-Tasks are marked exempt with a
  rationale in track state.
- **Backward moves**: `lifecycle.sh regress <id> --to <phase> --reason <text>` (logged).

## Providers (GitHub / GitLab / Linear / Jira)

Entry is a ticket URL or issue key; `lifecycle.sh init` detects the provider. Hierarchy
and status rendering come from `configs/claude/config/tracker_providers.yml`
(`lifecycle.sh status-map <provider> <canonical>` resolves a label vs. a Jira transition).

**Jira is reached via the pre-authenticated Atlassian MCP** (wired in `settings.local.json`)
— there is no bespoke auth (FR-020). Because MCP tools are an agent capability, the *agent*
(this skill) makes the calls and feeds results to `lifecycle.sh`. Call each tool by its
fully-qualified id `mcp__atlassian__<tool>` (server key `atlassian` in `settings.local.json`);
bare names fail to resolve when multiple MCP servers are connected:

| Lifecycle step | Atlassian MCP tool | Then |
|---|---|---|
| classify entry tier | `mcp__atlassian__getJiraProjectIssueTypesMetadata` | record tier on the track |
| read issue | `mcp__atlassian__getJiraIssue` / `mcp__atlassian__searchJiraIssuesUsingJql` | — |
| provision a node | `mcp__atlassian__createJiraIssue` (parent field set) | `lifecycle.sh provision … --external-id <new-key>` |
| apply status | `mcp__atlassian__getTransitionsForJiraIssue` → `mcp__atlassian__transitionJiraIssue` (by **id**, never free-text) | mirror canonical status |

For GitHub/GitLab (`git_ops.sh`) the provision backend is the `LIFECYCLE_PROVISION_CMD` seam
wrapping those CLIs, and status renders as a canonical **label** via `label_sync.sh`. Linear
(`linear_ops.sh`) uses the same seam but status renders as a workflow **state** (GraphQL
`transition-state`), not a label — per each provider's `status_via` in the config.

## Notes

- This skill never re-implements the phase commands (FR-001) and consumes the smoke runtime
  as-is (FR-012).
- The autodev loop consumes the same `lifecycle.sh gate` core for hard enforcement, so human
  and agent paths share one tested decision.
