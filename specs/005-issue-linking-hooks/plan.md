# Implementation Plan: Issue-Linking Git Hooks

**Branch**: `005-issue-linking-hooks` | **Date**: 2026-06-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-issue-linking-hooks/spec.md`

## Summary

Deliver two companion, hook-triggered skills — **`pr-issue-sync`** (fires when a pull/merge request is opened) and **`commit-issue-sync`** (fires when commits land on a feature branch) — over a single shared **issue-support engine** implemented as `configs/claude/scripts/issue_support.sh`, a platform-agnostic sibling to `git_ops.sh`. The engine resolves the linked issue(s) from branch-number prefix → PR/MR body references → commit-message references/trailers, then idempotently advances status labels (`planned`→`in-progress` on commit, for issues already labeled `planned`; →`needs-review` on PR), posts a back-link comment, ensures closing keywords, and — when no issue is found — offers to create a best-of-breed tracking issue (dedup-checked, templated, canonically labeled). All behavior is **fail-open** within a configurable soft timeout (`hook_timeout_seconds`, default 5s) and self-heals via idempotency. Triggering reuses the repo's existing `ai-hooks-integration` unified `PostToolUse` mechanism (cross-tool) matched to PR-create and commit commands, with a guarded native `post-commit` git hook installer as a fallback for raw-CLI usage.

## Technical Context

**Language/Version**: Bash (`set -euo pipefail`, matching `git_ops.sh`/`label_sync.sh`); Python 3 only for JSON/YAML parsing of `gh`/`glab` output and `command_config.yml`, mirroring the `label_sync.sh` precedent. `jq` used where `git_ops.sh` already uses it.

**Primary Dependencies**: Existing repo scripts — `git_ops.sh` (issue-view/issue-comment/issue-comment-edit-last/issue-edit/issue-create/issue-list/pr-view subcommands), `git_platform.sh` (github|gitlab|git detection), `labels.yml` + `label_sync.sh` (canonical labels), `ai-hooks-integration` (unified hook install). External CLIs `gh` and `glab` (invoked only through `git_ops.sh`, never directly). **New primitive required**: `git_ops.sh` currently has no PR-body write path, so this feature adds a minimal `git_ops.sh pr-edit <N>` subcommand (thin wrapper over `gh pr edit --body` / `glab mr update --description`) to support non-destructive closing-keyword insertion (FR-005). This is a natural sibling to the existing `pr-create`/`pr-merge`/`issue-edit` primitives — extending the platform-ops wrapper, not absorbing skill logic (Constitution IV-compatible).

**Storage**: None. Dedup/idempotency are derived from live tracker state (existing labels + a marker line in the engine's own back-link comment), not local files — so a timed-out or repeated run is self-correcting with no persisted state to drift.

**Testing**: `bats` shell tests in `tests/bats/issue_support.bats` (engine subcommands, resolution precedence, idempotency, fail-open); optional `pytest` in `tests/python/` for any Python parsing helper. Fixtures under `tests/fixtures/`.

**Target Platform**: macOS / Linux developer machines and CI (same surface as the rest of the repo).

**Project Type**: CLI / automation skill set (single-project shell-and-config layout).

**Performance Goals**: A hook adds ≤ `hook_timeout_seconds` (default 5s) to any git action; after the first commit on a branch, subsequent commits short-circuit to a sub-second no-op via dedup (SC-007).

**Constraints**: Fail-open (never abort PR creation or commit — SC-002); all mutations idempotent and forward-only; no new per-repo platform configuration beyond enabling the hook; conforms to repo script conventions (`err()`, `--help` ≤15 lines, `set -euo pipefail`).

**Scale/Scope**: Single repository, per-developer cadence; modest API-call volume (a handful of calls per PR/commit, dedup-bounded). v1 targets GitHub + GitLab per the feature request; Linear is an explicit extension point (see research.md), not v1 scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|-----------|-----------|--------|
| **I. Configuration-as-Code** | All artifacts land in `configs/` (engine script, config) and `.skillshare/skills/` (the two skills); nothing edits deployed `~/.claude` directly; hook install is reproducible. | ✅ PASS |
| **II. Parallel Agent Orchestration** | The engine handles a platform token and creates/mutates external issues; the change will exceed 200 lines. Tier 1 cross-verification via `parallel_agent.py` is REQUIRED at PR review (recorded as a process obligation, not a code change). | ✅ PASS (review gate noted) |
| **III. Consensus-Driven Decisions** | Applies at review time against the standard thresholds; no plan-level conflict. | ✅ PASS |
| **IV. Skill-First Extensibility** | New capability ships as two discrete, independently-invocable skills. The shared engine is a new sibling ops script (analogous to `git_ops.sh`/`linear_ops.sh`), NOT new behavior bolted onto `parallel_agent.py`. The one core-script edit — adding `pr-edit` to `git_ops.sh` — is a missing platform-ops primitive (sibling to existing `pr-create`/`pr-merge`/`issue-edit`), not skill logic absorbed into the core. | ✅ PASS |
| **V. Bootstrap Reproducibility** | Hook installation MUST be idempotent and guarded by existence checks (no duplicate hook entries; native `post-commit` installer refuses to clobber an existing hook). | ✅ PASS (idempotency requirement carried into design) |

**Result**: No violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/005-issue-linking-hooks/
├── plan.md              # This file
├── research.md          # Phase 0 output — trigger mechanism, dedup, Linear scope, PR detection
├── data-model.md        # Phase 1 output — entities & state transitions
├── quickstart.md        # Phase 1 output — enable/verify walkthrough
├── contracts/           # Phase 1 output
│   ├── issue_support_cli.md   # Engine subcommand contract
│   └── hook_contract.md       # Hook trigger/payload contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
configs/claude/
├── scripts/
│   ├── issue_support.sh          # NEW — shared engine (platform-agnostic; wraps git_ops.sh + git_platform.sh)
│   ├── install_issue_hooks.sh    # NEW — idempotent installer (unified PostToolUse + guarded native post-commit)
│   ├── git_ops.sh                # EDIT — add minimal `pr-edit <N>` subcommand (PR-body write path for closing-keyword insertion)
│   └── templates/
│       └── issue_support_issue.md # NEW — best-of-breed created-issue template (engine-owned; used by BOTH skills)
├── config/
│   ├── command_config.yml        # EDIT — tool_policies.pr-issue-sync: {enabled, hook_timeout_seconds}; tool_policies.commit-issue-sync: {enabled, hook_timeout_seconds, commit_hook_mode}. `enabled` defaults false (runtime gate the engine checks before acting); commit_hook_mode is commit-only.
│   └── labels.yml                # REUSE — canonical labels (no change)
└── skills/                       # symlink → ../../.skillshare/skills (do not replace)

.skillshare/skills/
├── pr-issue-sync/
│   └── SKILL.md                  # NEW — PR-triggered skill (invokes `issue_support.sh sync-pr`)
└── commit-issue-sync/
    └── SKILL.md                  # NEW — commit-triggered skill (invokes `issue_support.sh sync-commit`)

tests/
├── bats/
│   └── issue_support.bats        # NEW — engine + installer tests
└── fixtures/
    └── issue_support/            # NEW — mock pr-view / issue-view JSON payloads
```

**Structure Decision**: Single-project shell-and-config layout (repo default). The shared engine is a standalone script in `configs/claude/scripts/` so it is testable in isolation, manually invocable (`issue_support.sh --help`), and consumable by both skills plus the hook installer — exactly the pattern set by `git_ops.sh`, `linear_ops.sh`, and `label_sync.sh`. The two skills are thin SKILL.md wrappers that document invocation; they delegate all logic — including best-of-breed issue creation — to the engine. The created-issue template is **engine-owned** (`configs/claude/scripts/templates/issue_support_issue.md`) so it is resolved identically no matter which skill triggered the run.

## Complexity Tracking

> No constitution violations — table intentionally empty.
