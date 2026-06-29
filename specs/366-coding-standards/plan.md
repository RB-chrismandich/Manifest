# Implementation Plan: Coding Standards & Edit-Time Enforcement

**Branch**: `366-coding-standards` | **Date**: 2026-06-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/366-coding-standards/spec.md`

## Summary

Improve the Manifest repo's existing four-layer code-quality enforcement
(editor → edit-time → commit-time → gate-of-record) rather than rebuild it. Three
concrete changes deliver the spec:

1. **Edit-time language linting** — a new advisory PostToolUse hook
   (`lint_on_edit_hook.sh`) that lints the just-edited file by extension
   (`.sh`/`.py`/`.yml`/`.json`/`.md`/`.mdc`), never blocking, never auto-fixing,
   fail-open and time-bounded. Closes the gap that the only per-edit layer today
   lints nothing. (US1/P1)
2. **No-bypass gate of record** — CI runs the same `.pre-commit-config.yaml`
   against the files changed in each PR/push (refined 2026-06-29 from `--all-files`
   due to pre-existing debt), eliminating the CI↔pre-commit divergence that lets
   ruff/shfmt/gitleaks/markdown checks be skipped on new code. (US2/P2)
3. **Documented, current standards** — one authoritative `docs/CODING_STANDARDS.md`
   with an Active/Conditional/Document-only verdict per language; remediate
   stale/deprecated tooling (tfsec→Trivy, golangci-lint v2, version bumps, guarded
   dormant hooks); add a root `pyproject.toml`. (US3/P3, US4/P4)

## Technical Context

**Language/Version**: Bash (macOS Bash 3.2-compatible) for hooks/scripts; Python ≥3.11 for tooling config (`pyproject.toml`); YAML for `.pre-commit-config.yaml` + GitHub Actions.

**Primary Dependencies**: `pre-commit` framework; linters — shellcheck, shfmt, ruff (+ruff-format), yamllint, markdownlint-cli, gitleaks, golangci-lint v2 (dormant), pre-commit-terraform with `terraform_trivy`/`terraform_fmt`/`terraform_validate` (dormant), guarded `cargo fmt`/`clippy` (dormant), pyright (type-check). GitHub Actions for CI.

**Storage**: N/A — all artifacts are version-controlled config/docs/scripts.

**Testing**: bats (`tests/bats/`) for `lint_on_edit_hook.sh`; pytest (`tests/python/`) where applicable; the pre-commit suite runs on changed files in CI (with `--all-files` available for local sweeps) as the integration gate; existing CI ≥100-test floor preserved.

**Target Platform**: Developer machines (macOS Intel/Apple Silicon, Linux) for hooks/pre-commit; Ubuntu GitHub Actions runners for CI.

**Project Type**: Single project — CLI/configuration-management repo (agent-orchestration configs deployed to `~/` via `bootstrap.sh`).

**Performance Goals**: Edit-time hook adds < ~1s typical per edit; each linter hard-capped (timeout 8s where a timeout binary exists) and fail-fast; CI `pre-commit run` completes within the existing CI time budget (dormant hooks skip on no matching files, so no golangci/terraform/trivy install cost).

**Constraints**: Edit-time hook MUST always `exit 0`, MUST NOT auto-fix, MUST fail-open (missing tool → skip), MUST be macOS Bash 3.2-safe (no `timeout` binary present locally → graceful fallback), and MUST follow repo conventions (`err()` for internal errors, `--help` ≤15 lines). No manual edits to deployed `~/.claude/` files — source lives in `configs/`.

**Scale/Scope**: ~46 `.sh`, ~40 `.bats`, ~91 `.py`, ~303 `.md`, ~90 `.mdc`, ~57 YAML, ~33 `.json` tracked files; 4 enforcement layers; 11 languages catalogued.

**Unknowns**: None — all 3 spec `[NEEDS CLARIFICATION]` markers resolved in `/speckit-clarify` (Session 2026-06-28).

## Constitution Check

*GATE: Must pass before Phase 0. Re-checked after Phase 1 (below).*

| Principle | Verdict | Notes / Gate |
|---|---|---|
| I. Configuration-as-Code | **PASS** | New hook lives in `configs/claude/scripts/lint_on_edit_hook.sh`; wired via `configs/claude/settings.local.json`; deployed by `bootstrap.sh`. `.pre-commit-config.yaml`, `ci.yml`, `pyproject.toml`, `.editorconfig`, `docs/` are repo-root infra (not deployed to `~/`). No manual `~/.claude/` edits. |
| II. Parallel Agent Orchestration | **APPLIES** | Change parses an external JSON payload + invokes subprocesses (security-adjacent) and aggregate diff > 200 lines → PR MUST be cross-verified by ≥2 agents (`parallel_agent.py`) before merge. Satisfied at the `/speckit-implement-review` + PR stage. |
| III. Consensus-Driven Decisions | **PASS (deferred to review)** | Cross-verification at PR time must meet the ≥80/50–79/<50 thresholds. |
| IV. Skill-First Extensibility | **PASS** | The edit-time hook is infrastructure (a PostToolUse adapter, like `version_pin_hook.sh`/`spec_review.sh`), not a new user-invocable capability; no new behavior is bolted onto `parallel_agent.py`. |
| V. Bootstrap Reproducibility | **PASS** | Deployment is an idempotent file copy; plan includes a `chmod +x` guarantee for the new script. No non-idempotent operations introduced. |
| Quality Gates / Dev Workflow | **PASS w/ obligations** | New shell script REQUIRES bats coverage (`tests/bats/lint_on_edit_hook.bats`); YAML configs validated; CI must stay green and keep ≥100 tests. |

**Result**: No violations requiring Complexity Tracking. Gate II is an obligation discharged at review/PR, not a blocker for design.

## Project Structure

### Documentation (this feature)

```text
specs/366-coding-standards/
├── spec.md              # Feature spec (clarified)
├── plan.md              # This file
├── research.md          # Phase 0 decision record
├── research-notes.md    # Pre-spec multi-agent research dossier (supporting)
├── data-model.md        # Phase 1: config/data entities
├── quickstart.md        # Phase 1: how to verify
├── contracts/           # Phase 1: behavioral contracts
│   ├── edit-time-hook.md
│   └── enforcement-gates.md
└── checklists/
    └── requirements.md  # Spec quality checklist (passing)
```

### Source Code (repository root)

```text
configs/claude/
├── scripts/
│   └── lint_on_edit_hook.sh        # NEW — advisory edit-time language linter
└── settings.local.json             # MODIFIED — add 3rd PostToolUse Write|Edit hook

.pre-commit-config.yaml             # MODIFIED — version bumps; tfsec→trivy; +terraform_fmt/validate;
                                    #            golangci v2; +pyright (local); +.mdc markdownlint;
                                    #            +check-ast/debug-statements; guarded Rust hook
.github/workflows/ci.yml            # MODIFIED — lint job runs pre-commit on CHANGED files
                                    #            (+pre-commit cache); keep non-hook checks
pyproject.toml                      # NEW — [tool.ruff], requires-python, pytest/coverage, pyright
.editorconfig                       # MODIFIED — add [*.ps1], [*.mdc], [*.bats] rules
docs/CODING_STANDARDS.md            # NEW — authoritative per-language standard + verdicts

tests/bats/
└── lint_on_edit_hook.bats          # NEW — dispatch, exit-0, no-mutation, fail-open, excludes
tests/python/ (or tests/lint/)      # (optional) config-validity assertions

CLAUDE.md / .claude/CLAUDE.md / CONTRIBUTING.md / AGENTS.md   # MODIFIED — link the standards doc
```

**Structure Decision**: Single-project layout. The deployable runtime artifact
(the hook script + its hook wiring) lives under `configs/claude/` per
Configuration-as-Code; repo-infra files (`.pre-commit-config.yaml`, `ci.yml`,
`pyproject.toml`, `.editorconfig`, `docs/`) stay at the repo root where their
tools expect them.

## Phase 0 — Research

All decisions are consolidated in [research.md](./research.md) (decision /
rationale / alternatives), grounded by the multi-agent dossier in
[research-notes.md](./research-notes.md). No open unknowns remain.

## Phase 1 — Design & Contracts

- Entities (config/data shapes) → [data-model.md](./data-model.md)
- Behavioral contracts → [contracts/edit-time-hook.md](./contracts/edit-time-hook.md), [contracts/enforcement-gates.md](./contracts/enforcement-gates.md)
- Verification walkthrough → [quickstart.md](./quickstart.md)
- Agent context: the `<!-- SPECKIT START/END -->` block in `CLAUDE.md` is updated to point here.

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1: design introduces no new principle violations. The
edit-time hook mirrors the existing advisory-hook contract (exit 0, fail-open),
keeping Principle IV intact; deployment remains an idempotent copy (Principle V);
the only standing obligation is the Gate II parallel-agent cross-verification at
PR time. **No Complexity Tracking entries required.**

## Complexity Tracking

No constitution violations — table intentionally empty.
