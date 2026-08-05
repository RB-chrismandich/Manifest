# Implementation Plan: emdash Support (Full Config Inheritance)

**Branch**: `483-emdash-support` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/483-emdash-support/spec.md`

## Summary

emdash is an external Electron desktop app that runs the user's existing agent CLIs (Claude Code, etc.) in parallel git worktrees, spawned with the **real `HOME`** and the worktree as the working directory. A Manifest-configured agent therefore **already inherits the full Manifest configuration transitively** — home `~/.claude/` skills/subagents/hooks/MCP/orchestration-guide/settings plus the worktree's committed `CLAUDE.md`/`.claude/`/`AGENTS.md`. There is **no `~/.emdash/` config directory and no `configs/emdash/` deploy tree** to build (they would be inert; FR-008).

The technical approach is therefore **recognition + verification + gap-closing**, not deployment:

1. **A shared inheritance probe** (`configs/claude/scripts/emdash_inherit_check.sh`) that, given a `HOME` and a worktree path, reports whether each inheritance dimension (skills, subagents, hooks, MCP, orchestration guide, repo guides) is resolvable — and whether Manifest's hooks survive emdash's injected hook wiring. This single probe backs both the automated test and the live diagnostic.
2. **A hybrid verification** (per clarify Q1): a bats test (`tests/bats/emdash_inheritance.bats`) drives the probe against a synthetic fixture that reproduces emdash's launch environment (real-`HOME` layout, worktree cwd, injected `EMDASH_HOOK_*`, and a simulated emdash hook-merge into `.claude/settings.local.json`); plus a documented one-time **manual smoke** run against the real emdash app.
3. **A committed `.emdash.json`** (repo root) so fresh emdash worktrees of this repo are functional — `preservePatterns` for untracked local files and `scripts.setup`/`shellSetup` for environment setup (US2).
4. **Coexistence handling** (per clarify Q2): rely on emdash's idempotent, marker-based hook merge (observed: it appends its hook as `Stop: [emdashHook, userHook]`, preserving existing entries) — the probe/test *verify* Manifest's hooks survive; `docs/EMDASH.md` documents the `.gitignore`/tracked-file interaction. No guard/restore, no untracking (FR-007).
5. **Recognition**: env-check gains an emdash inheritance section; config-audit gains a coexistence note; `docs/EMDASH.md` + README/GETTING_STARTED/AGENTS.md entries describe emdash as a supported harness with prerequisites.

Formally verified agent: **Claude Code**; Codex/Gemini/Cursor documented as best-effort transitive inheritance (clarify Q3).

## Technical Context

**Language/Version**: Bash (POSIX sh + bash 3.2+, matching `bootstrap/` and `configs/claude/scripts/`), Python 3.11 (uv-managed, `pyproject.toml`) for any helper/assertions, JSON (`.emdash.json`), Markdown (docs).

**Primary Dependencies**: `git` (worktrees), `jq` (JSON assertions in shell), the **emdash desktop app** (external, user-installed — not a Manifest dependency), **Claude Code CLI** (primary verified agent). No new runtime dependencies introduced.

**Storage**: Files only — a repo-committed `.emdash.json`, a probe script, a bats test + fixtures, and docs. No database, no home-directory deploy target.

**Testing**: `bats-core` (`tests/bats/`, submodule helpers per `.gitmodules`), `pytest` (`tests/python/`), `shellcheck`, `yamllint`; mirrors the existing `deploy_antigravity.bats` / `deploy_skills.bats` conventions and the CI changed-file gate.

**Target Platform**: Developer machines (macOS/Linux) that have run the Manifest home deployment (`bootstrap.sh`) and installed the emdash desktop app.

**Project Type**: Repository tooling / cross-agent config-deployment system (single project — the Manifest repo). Not an application; no `src/` app tree.

**Performance Goals**: The inheritance probe MUST complete in < 2 s so it can run inline in `/env-check`. No other performance constraints (this is a config/verification feature).

**Constraints**:
- MUST NOT create `~/.emdash/` or `configs/emdash/` (FR-008) — support is transitive.
- MUST follow repo script conventions: `err()` for error output, `--help` on user-facing scripts (`docs/CODING_STANDARDS.md`, `.claude/CLAUDE.md`).
- MUST pass the real pre-commit / CI changed-file gate (shellcheck, yamllint, shebang-exec, EOF) — see the "no-bypass gate blast radius" lesson.
- Any edit to a Claude-auto-loaded guide (root `CLAUDE.md`) MUST stay within `context_budget.bats`; keep CLAUDE.md changes to the SPECKIT block only.
- Secrets in `preservePatterns` MUST never be committed (FR-006 acceptance 3).

**Scale/Scope**: ~1 new script, 1 `.emdash.json`, 1 bats test (+ fixtures), env-check + config-audit edits, 1 new `docs/EMDASH.md`, entries in README/GETTING_STARTED/AGENTS.md, and the CLAUDE.md SPECKIT block. Small–medium, additive, no breaking changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No speckit `constitution.md` exists in this repo; governance is codified in `CLAUDE.md`, `configs/claude/config/validation_criteria.yml`, and the state-gated lifecycle (spec 365). Mapped gates:

| Gate | Status | Notes |
|------|--------|-------|
| **State-gated lifecycle** (specify→clarify→plan→tasks→implement→verify, no skips) | ✅ PASS | This feature is flowing through the phases in order. |
| **Verify gate backed by a smoke/critical-path test** | ✅ PASS | The user-facing workflow (run Manifest via emdash) is gated by the automated inheritance probe test + a documented manual smoke (FR-011). |
| **Tier 1 — security** (`validation_criteria.yml`) | ✅ PASS | Only security-relevant surface is `preservePatterns` moving untracked files into worktrees; spec forbids committing secrets (FR-006 AC3), documented in `docs/EMDASH.md`. |
| **Tier 1 — error handling / breaking changes** | ✅ PASS | Additive only; no existing deploy path changes; probe fails closed (non-zero exit) and routes messages through `err()`. |
| **Tier 1 — cross-verification** | ✅ PASS | Design cross-checked by two research agents + on-disk empirical evidence; `/spec-review` recommended before `/speckit-implement`. |
| **Token-economy / context_budget** | ✅ PASS | CLAUDE.md change limited to the SPECKIT block; emdash docs live in `docs/`, not auto-loaded guides. |

**Result**: No violations. Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/483-emdash-support/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output — decisions + rationale
├── data-model.md        # Phase 1 output — entities (.emdash.json, dimensions, probe report)
├── quickstart.md        # Phase 1 output — user setup + verification runbook
├── contracts/
│   ├── emdash-project-config.md   # .emdash.json schema + this repo's concrete values
│   └── inheritance-probe.md       # probe CLI contract + fixed inheritance-dimension checklist
├── spec.md              # Feature spec (/speckit-specify + /speckit-clarify)
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
# NEW files
.emdash.json                                   # emdash project config (preservePatterns, scripts.setup, shellSetup)
configs/claude/scripts/emdash_inherit_check.sh # inheritance probe (shared by env-check + bats test); err()/--help
tests/bats/emdash_inheritance.bats             # automated launch-env simulation test (FR-011a)
tests/bats/fixtures/emdash/                     # synthetic HOME + worktree + emdash-merged settings fixtures
docs/EMDASH.md                                  # emdash usage, prerequisites, coexistence caveat (FR-009, FR-012)

# MODIFIED files
.retired skill supply/skills/env-check/SKILL.md           # add "emdash Inheritance" check calling the probe (FR-010)
.retired skill supply/skills/config-audit/SKILL.md        # add emdash hook-coexistence awareness note (FR-010)
README.md                                       # "Running agents via emdash" pointer → docs/EMDASH.md
docs/GETTING_STARTED.md                          # "Using Manifest with emdash" subsection
AGENTS.md                                        # brief note: emdash-launched agents inherit config transitively
CLAUDE.md                                        # SPECKIT block → point at 483 (SPECKIT markers only)
.github/workflows/ci.yml                         # (only if needed) ensure new bats test runs in the suite
```

**Structure Decision**: Single-project repo tooling. No `src/` app tree — the feature adds one shared shell probe, one bats test + fixtures, one committed `.emdash.json`, skill/doc edits, and a docs page. It deliberately touches **none** of the platform-deploy machinery (`bootstrap/lib/deploy.sh`, `config.sh` services.yml, `configs/claude/scripts/agents/*.py` provider registration) because emdash is neither a deploy target nor a parallel-agent provider (FR-008; Non-Goals).

## Complexity Tracking

> No Constitution Check violations. No entries.
