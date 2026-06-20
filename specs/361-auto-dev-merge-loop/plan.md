# Implementation Plan: Autonomous PR Lifecycle & Merge Loop

**Branch**: `361-auto-dev-merge-loop` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/361-auto-dev-merge-loop/spec.md`

## Summary

Extend the `auto-issue-dev` loop past PR-open: monitor each automation-authored PR for
actionable comments and pipeline failures, remediate via the existing `/address-pr-comments`,
`/pr-review`, and `/verify` skills across ≤3 revision cycles, and **merge to main** (admin
bypass) only when every safety signal clears. Add self-paced advancement with a 10-minute
per-run ceiling, a stop-after-5-empty-runs control, serialized merges with interleaved
monitoring, and a halt-on-post-merge-breakage guard. The implementation is a set of
**testable shell helpers** plus extensions to the `auto-issue-dev` skill — it *consumes*
`parallel_agent.py` and the #360 verification gate; it does not modify them.

## Technical Context

**Language/Version**: Bash (macOS bash 3.2+ / Linux), Python 3.11 for JSON/decision helpers
(consistent with repo conventions).

**Primary Dependencies**: `gh` (GitHub) / `glab` (GitLab) via `git_ops.sh` + `git_platform.sh`;
`parallel_agent.py` (consensus engine); the #360 `verification_gate.sh`; existing skills
`/address-pr-comments`, `/pr-review`, `/verify`; `audit_log.sh` (audit + redaction); `jq`;
the `/loop` harness that re-invokes the skill with fresh context.

**Storage**: files only — append-only audit log (`audit_log.sh`); a concurrency lock + an
empty-run counter in a known state dir; no database.

**Testing**: `bats` (`tests/bats/`) for shell helpers and the deterministic decision cores;
`pytest` (`tests/python/`) for any Python; `shellcheck` + `yamllint` lint gates.

**Target Platform**: macOS + Linux CLI (developer machine or unattended runner).

**Project Type**: CLI automation / skill orchestration (single project).

**Performance Goals**: self-paced advancement (act the moment state is actionable); hard
per-run ceiling default 10 min (FR-017a); at most one merge-to-main in flight (FR-014).

**Constraints**: fail-closed on every indeterminate safety signal (FR-020); secret redaction
on all reviewer/log/comment content (FR-022); idempotent + existence-guarded state (Principle
V); ARG_MAX-safe reviewer seam (reuse `headless-llm-cli-seam`); hard dependency on the #360
verification gate.

**Scale/Scope**: a single repo's open-PR queue (a handful to a few dozen PRs); one merge
serialized at a time.

**Resolved in Phase 0 research** (see [research.md](./research.md)): exact `gh` mechanics for
(1) admin-bypass merge + pre-flight admin-capability detection, (2) actionable-comment /
review-state classification, (3) PR + post-merge-`main` CI status (pass/pending/fail),
(4) one-attempt conflict update, concurrency guard, and branch prune.

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1 design (below).*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Configuration-as-Code | ✅ PASS | All logic in `configs/claude/scripts/`, `.skillshare/skills/`, `.specify/`, `configs/claude/config/`; deployed via `bootstrap.sh`. No manual `~/.claude` edits. |
| II. Parallel Agent Orchestration | ⚠️ PASS w/ design constraint | Security-sensitive change (merge authority). The runtime honors it: **no PR is auto-merged without parallel-agent cross-verification** (the #360 gate runs `parallel_agent.py` as a merge precondition). Crucially, **for the merge gate, consensus `cross_verification` is BLOCKING** — stricter than #360's PR-open gate where it is advisory. The bar to *merge autonomously* is higher than the bar to *open a PR*. See Complexity Tracking. |
| III. Consensus-Driven Decisions | ✅ PASS | The merge decision references the canonical thresholds: consensus ≥0.80 → eligible to auto-merge; 0.50–0.79 → hand to human (do not auto-merge); <0.50 → block + synthesize. No consensus bypass — the gate *runs* consensus, it does not skip it. |
| IV. Skill-First Extensibility | ✅ PASS | Implemented as `auto-issue-dev` skill extensions + discrete testable shell helpers. `parallel_agent.py` is *consumed*, never expanded (Principle IV prohibition respected). |
| V. Bootstrap Reproducibility | ✅ PASS | New scripts are idempotent; lock/counter state is existence-guarded; scripts exit non-zero on unrecoverable failure. |

**Quality-gate note (breaking change)**: this feature **supersedes `auto-issue-dev` Critical
Rule #1 ("never merge")**. That is a deliberate behavior change and MUST be called out as a
breaking change in the feature's own PR (Tier-1 "breaking changes" gate), with the SKILL.md
rule updated, not silently contradicted.

## Project Structure

### Documentation (this feature)

```text
specs/361-auto-dev-merge-loop/
├── plan.md              # This file
├── research.md          # Phase 0 — verified gh/git mechanics (4 research agents)
├── data-model.md        # Phase 1 — entities + state machine
├── quickstart.md        # Phase 1 — how to run / dry-run the loop
├── contracts/           # Phase 1 — CLI contracts for new script subcommands
└── tasks.md             # Phase 2 — created by /speckit-tasks (NOT here)
```

### Source Code (repository root)

```text
configs/claude/scripts/
├── pr_merge_loop.sh         # NEW — orchestrates monitor → address → merge per managed PR;
│                            #   subcommands: list-managed, monitor <pr>, address-cycle <pr>,
│                            #   post-merge-check, empty-run (get/incr/reset). Self-paced
│                            #   with a ceiling; fail-closed; reuses git_ops.sh.
├── merge_decision.sh        # NEW — PURE deterministic core (no I/O): decide <signals-json>
│                            #   → {action: merge|revise|hand-human|halt, reason}. Fully
│                            #   bats-tested offline. Mirrors #360 verification_gate.sh decide.
├── loop_lock.sh             # NEW — concurrency guard (acquire/release/is-held) per PR.
├── git_ops.sh               # REUSE/extend — pr-merge (admin/squash/delete-branch), issue/PR
│                            #   view, comment, label; review-state + checks accessors if absent.
├── verification_gate.sh     # PREREQUISITE (#360 — NOT YET BUILT, design only): its Tier-1
│                            #   verdict + consensus feed the merge precondition. BLOCKS T018–T023.
├── audit_log.sh             # REUSE — append + redact.
└── git_platform.sh          # REUSE — platform detection (gate logic branches github/gitlab).

configs/claude/config/
├── validation_criteria.yml  # EDIT — NEW `command_overrides.auto-issue-dev-merge` (distinct
│                            #   from #360's advisory `auto-issue-dev`): cross_verification BLOCKING.
├── command_config.yml       # EDIT — reconcile auto-issue-dev tool policy (gate/merge uses
│                            #   parallel agents deliberately).
└── labels.yml               # EDIT — add `ready-to-merge`, `loop-active` (lock), `hold`;
                             #   reuse existing `needs-human`, `blocked-dependency`.

.skillshare/skills/auto-issue-dev/
└── SKILL.md                 # EDIT — supersede Rule #1; add the monitor/merge phase + loop
                             #   controls (self-pace, ceiling, empty-run stop, serialized merge).

tests/bats/
├── merge_decision.bats      # NEW — every branch of the decision core.
├── pr_merge_loop.bats       # NEW — orchestration via injected seams (offline).
└── loop_lock.bats           # NEW — acquire/release/contention.
```

**Decision rationale**: the safety logic lives in `merge_decision.sh` as a **pure, offline-
testable core** (the same pattern #360 used for `verification_gate.sh decide`), because this
change "reshapes the autonomy pipeline" and the irreversible merge must be defensible and
unit-tested, not buried in skill prose.

## Complexity Tracking

| Deviation | Why needed | Why a simpler alternative is insufficient |
|-----------|-----------|-------------------------------------------|
| Admin-bypass merge removes human review from the happy path | The feature's explicit goal (user decision: auto-merge w/ admin bypass). Single-maintainer repo; the bot author cannot self-approve. | "Prepare, never merge" was offered and rejected by the user. Safety is preserved by replacing human review with automated cross-verification (CI + `/verify` + `/pr-review` + #360 gate + **blocking** consensus), satisfying Principle II in substance. |
| Consensus `cross_verification` is **blocking** for the merge gate (stricter than #360 PR-open) | Honors Principle II for the most irreversible action. | Reusing #360's advisory-consensus override verbatim would let a <80%-consensus change auto-merge with no human — a Principle II violation. The merge gate uses its own override with `cross_verification` in Tier-1. |
| New orchestration + decision scripts (not pure skill prose) | The merge is irreversible; its decision logic must be bats-tested offline. | Skill-only logic can't be unit-tested deterministically; the repo's convention is testable shell helpers (`auto_issue_dev.sh`, `verification_gate.sh`). |

## Phase 0 — Outline & Research

Unknowns dispatched to parallel research agents (Principle II — verify, don't assume),
consolidated in [research.md](./research.md):
1. Admin-bypass merge + pre-flight admin-capability detection (fail-closed for FR-008/FR-009).
2. Actionable-comment / review-state classification (FR-007a).
3. PR check status + post-merge `main` CI health, distinguishing **pending vs failing**
   (FR-001, FR-012a, FR-017).
4. One-attempt conflict update (`mergeStateStatus`), concurrency guard, branch prune (FR-010,
   FR-011, FR-023).

Self-pacing/ceiling mapping onto `/loop` + `ScheduleWakeup` (prompt-cache window awareness)
and the automation-author allowlist mechanism are resolved from existing repo knowledge in
research.md.

## Phase 1 — Design & Contracts

- `data-model.md`: the **managed-PR state machine** (monitoring → addressing → verified →
  merged | needs-human | halted) and entities (work item, revision cycle, clear conditions,
  empty-run counter, audit record, automation-author allowlist).
- `contracts/`: CLI contracts (inputs/outputs/exit codes) for `merge_decision.sh decide`,
  `pr_merge_loop.sh` subcommands, and `loop_lock.sh` — these are the testable seams.
- `quickstart.md`: how to dry-run the loop (`--apply` off), force a single PR through, and
  observe the audit trail.
- Agent context: update the `<!-- SPECKIT START -->…END -->` marker in the root `CLAUDE.md`
  to point at this plan.

## Phase 2 — (handled by `/speckit-tasks`, not here)

Tasks will be dependency-ordered: decision core + tests first (offline), then orchestration
seams, then config/labels, then SKILL.md supersession, then live wiring.
