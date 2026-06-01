# Implementation Plan: New Agent Skills (Version Pinning, Docs Orchestration, PR Review, Branch Cleanup)

**Branch**: `002-new-agent-skills` | **Date**: 2026-06-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-new-agent-skills/spec.md`

## Summary

Add four discrete, independently-invocable Claude Code skills to the Manifest
configuration repository, each authored as a `SKILL.md` under
`.skillshare/skills/<name>/` (source of truth), registered in
`command_config.yml` tool policies and `validation_criteria.yml` overrides, and
documented in the repo's command listings:

1. **`version-pin`** — detect loose dependency references (`latest`, missing version,
   unbounded range, missing hash) in recognized files; resolve specific versions + integrity
   hashes via **native package-manager tooling**; auto-fix in place on explicit invocation,
   **warn-only** when fired from the save-triggered hook; explicit per-entry bypass.
2. **`docs-all`** — orchestrate the existing `docs-readme` / `docs-diagrams` / `docs-improve`
   skills as sub-agents, choosing order per run with a documented default precedence fallback,
   aggregating one consolidated report.
3. **`pr-review`** — enumerate all open PRs via the existing `git_ops.sh` abstraction, recommend a
   disposition per PR, analysis-only by default.
4. **`branch-clean`** — identify merged / `[gone]` / stale branch candidates, dry-run by default,
   **local-only** deletion by default with remote deletion behind an explicit flag, never touching
   protected/current branches.

Technical approach: skills are Markdown instruction documents (prompt-as-program), not compiled
code. `version-pin`, `pr-review`, and `branch-clean` are backed by new shell helper scripts under
`configs/claude/scripts/` (consistent with `git_ops.sh`, `label_sync.sh`); `docs-all` is pure
orchestration via the Agent/sub-agent mechanism with no new script. The `version-pin` hook is wired
through the existing `ai-hooks-integration` skill / `settings` hooks mechanism, not a new framework.

## Technical Context

**Language/Version**: Bash (POSIX-leaning, shellcheck-clean) for helper scripts; Markdown for SKILL.md instruction bodies; Python 3 only where a YAML/parse helper is unavoidable (mirrors existing repo scripts).

**Primary Dependencies**: Existing repo scripts (`git_ops.sh`, `git_platform.sh`); platform CLIs `gh` / `glab`; native package managers invoked on demand (`pip`/`pip-compile`, `docker` manifest/buildx, `npm`) — all degrade to reported warnings when absent.

**Storage**: Files only — target dependency files in the working tree, plus repo config YAML (`command_config.yml`, `validation_criteria.yml`). No database.

**Testing**: `bats tests/bats/` for shell helpers; `pytest tests/python/` for any Python helper; `shellcheck` + `yamllint` lint gates per the constitution.

**Target Platform**: Developer macOS/Linux workstations running Claude Code (and the Cursor/Gemini/Codex/Antigravity deploy targets via symlink).

**Project Type**: Agent-configuration repository — skills + supporting shell scripts (single project).

**Performance Goals**: Not throughput-bound; interactive CLI skills. `version-pin` resolution latency is dominated by package-manager/registry calls and is bounded only by being non-blocking on the hook path (warn-only).

**Constraints**: Idempotent (`version-pin` second run = no-op; SC-002); no silent failures (constitution Tier 1); analysis-only / dry-run defaults for destructive operations; `configs/claude/skills` must remain a symlink.

**Scale/Scope**: 4 new skills, ~3 new shell helper scripts, 2 config-file edits, doc updates, and a hook registration recipe. Tens-to-hundreds of dependency lines / PRs / branches per run.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Configuration-as-Code | ✅ PASS | All four skills + scripts live in `configs/`/`.skillshare/`, deployed via `bootstrap.sh`. No manual edits to deployed `~/.claude`. |
| II. Parallel Agent Orchestration | ✅ PASS | `version-pin` is security-sensitive (supply chain) → flagged for parallel-agent review at PR time. `docs-all` itself *is* a multi-sub-agent orchestrator. |
| III. Consensus-Driven Decisions | ✅ PASS | New skills inherit the standard consensus thresholds; `version-pin` set to Tier 1. |
| IV. Skill-First Extensibility | ✅ PASS | Each capability is a discrete `SKILL.md`; no expansion of `parallel_agent.py`. Helper scripts are siblings of existing `git_ops.sh`, not core-engine changes. |
| V. Bootstrap Reproducibility | ✅ PASS | Skills are files copied by existing `deploy_home_skills`; no new install step. Hook registration is idempotent (guarded). |

**Result**: PASS — no violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/002-new-agent-skills/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output — CLI command schemas per skill
│   ├── version-pin.md
│   ├── docs-all.md
│   ├── pr-review.md
│   └── branch-clean.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
.skillshare/skills/                  # Source of truth for skills
├── version-pin/SKILL.md             # NEW — pinning skill instruction body
├── docs-all/SKILL.md                # NEW — docs orchestration
├── pr-review/SKILL.md               # NEW — open-PR triage
└── branch-clean/SKILL.md            # NEW — branch cleanup
# (configs/claude/skills is a symlink → .skillshare/skills; not modified directly)

configs/claude/scripts/
├── version_pin.sh                   # NEW — detect/resolve/rewrite pinning logic
├── pr_review.sh                     # NEW — enumerate + assess open PRs (wraps git_ops.sh)
├── branch_clean.sh                  # NEW — identify + (confirm) delete branch candidates
├── git_ops.sh                       # EXISTING — reused by pr_review.sh / branch_clean.sh
└── git_platform.sh                  # EXISTING — reused for platform detection

configs/claude/config/
├── command_config.yml               # EDIT — add tool_policies for 4 skills + pinning rule set
└── validation_criteria.yml          # EDIT — add command_overrides for 4 skills

configs/claude/hooks/ (or settings)  # EDIT — register version-pin warn-only hook recipe
                                     #        via ai-hooks-integration conventions

tests/
├── bats/
│   ├── version_pin.bats             # NEW — pin detection/rewrite/idempotency/bypass
│   ├── pr_review.bats               # NEW — enumeration + disposition + analysis-only
│   └── branch_clean.bats            # NEW — candidate grouping + protected/dry-run safety
└── python/                          # (only if a Python parse helper is introduced)

docs/COMMANDS.md                     # EDIT — list the 4 new skills
CLAUDE.md / configs/claude/CLAUDE.md # EDIT — add skills to command tables
```

**Structure Decision**: Single-project layout matching the existing repo. Skills are
instruction Markdown in `.skillshare/skills/`; their non-trivial logic lives in
companion shell scripts under `configs/claude/scripts/` (the established pattern set by
`git_ops.sh` and `label_sync.sh`), keeping SKILL.md bodies focused on workflow and the
scripts independently testable via `bats`. `docs-all` needs no script — it is pure
sub-agent orchestration.

## Complexity Tracking

> No constitution violations. Section intentionally empty.
