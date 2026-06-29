---
name: lifecycle
description: Drive a unit of work through the codified state-gated development lifecycle (Specify→Clarify→Spec-Review→Plan→Task Creation→Analyze→Spec-Review tech→Implement→Verify). Use to start, advance, inspect, or regress a tracked feature/issue; enforces phase order (hard-halt for agents, advisory for humans) and the smoke-test Verify gate. Entry is a ticket URL or issue key (GitHub/GitLab/Linear/Jira).
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
| 9 | verify | `/speckit-implement-review` + `smoke_test.py run --tier Lite` | runner: exit 0 |

> Until the `--mode` flag ships (task T036), set `SPEC_REVIEW_TEMPLATE`/`SPEC_REVIEW_STATE`
> env vars directly to distinguish the product vs technical passes.

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
- **Verify**: backed by the smoke orchestrator. Missing coverage (`smoke_test.py run` exit 2,
  EMPTY) is a failure — never a pass. Non-user-facing Sub-Tasks are marked exempt with a
  rationale in track state.
- **Backward moves**: `lifecycle.sh regress <id> --to <phase> --reason <text>` (logged).

## Notes

- This skill never re-implements the phase commands (FR-001) and consumes the smoke runtime
  as-is (FR-012).
- The autodev loop consumes the same `lifecycle.sh gate` core for hard enforcement, so human
  and agent paths share one tested decision.
