# Implementation Plan: Skill Library Consolidation & Repo Health Hardening

**Branch**: `003-skill-library-consolidation` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-skill-library-consolidation/spec.md`

## Summary

Consolidate 19 skills across 6 duplicate clusters into 7 survivors (81 → 69
skills, −12), propagate deletions to deploy targets via mirror semantics,
stop future duplicates at the source (evolve library prompt gains
descriptions), then restore documentation accuracy (counts, four command
tables unified to docs/COMMANDS.md, changelog, stale reports), harden script
robustness (argv-passing into `python3 -c`, evolve chunk timeout, empty-array
guard in pre-commit + CI, relocate misplaced test files), close test/CI gaps
(learning_capture/check_status/generate_cursor_rules coverage; CI pinning +
caching), and finish hygiene items (gitignore `records/`, archive delivered
spec 002, `err()` convention + `--help` coverage). Delivered as one PR per
user story, P1 → P5.

## Technical Context

**Language/Version**: Bash 3.2-compatible shell (macOS default target) + Python 3.11 (no new deps)

**Primary Dependencies**: rsync, git, gh CLI, pre-commit, bats-core, pytest, PyYAML (all already in use)

**Storage**: Files only — `.skillshare/skills/` (source of truth), deploy targets under `~/`, YAML configs

**Testing**: bats (`tests/bats/`), pytest (`tests/python/`), shellcheck, yamllint, pre-commit; CI = `.github/workflows/ci.yml`

**Target Platform**: macOS (Bash 3.2) + Linux (CI ubuntu)

**Project Type**: Configuration/automation monorepo (CLI scripts + skill library + docs)

**Performance Goals**: CI median ≥20s faster via dependency caching (SC-008); evolve chunk bounded at 600s default (R3)

**Constraints**: Bash 3.2 compatibility (`set -u` empty-array semantics); skill-library changes only via PR review (Constitution IV + spec FR-004); no new runtime dependencies

**Scale/Scope**: 81 skills → 69; ~25 shell scripts swept; 4 docs unified; 3 new bats suites; 5 PRs

## Constitution Check

*GATE: evaluated against Manifest Constitution v1.0.0 — PASS (pre-Phase-0 and re-checked post-Phase-1).*

| Principle | Compliance |
|---|---|
| I. Configuration-as-Code | Strengthened: prune-on-deploy makes deploy targets converge to the repo source of truth; `records/` ambiguity removed. No manual deploy-target edits introduced. |
| II. Parallel Agent Orchestration | The consolidation PR rewrites >200 lines of skill content → cross-verify with parallel agents before merge (review gate noted in tasks). The P3 robustness PR touches security-adjacent quoting → same gate applies. |
| III. Consensus-Driven Decisions | Standard thresholds apply to the parallel reviews above; no bypasses planned. |
| IV. Skill-First Extensibility | Consolidation edits skills in `.skillshare/skills/` via PR; survivors keep valid `name`/`description` frontmatter and stay independently invocable. No core-script absorption of skill behavior. |
| V. Bootstrap Reproducibility | `deploy_home_skills` gains manifest-scoped prune-on-deploy (removes only skills it previously deployed that left the source; externally-added skills preserved — see contracts/prune-on-deploy.md) → *more* idempotent (converges to source). Bats coverage added for the new behavior. |
| Quality Gates | Each story-PR runs full bats + pytest + lint; Tier 1 security check covers the FR-009 quoting fixes. |

**Violations**: none. Complexity Tracking table intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-skill-library-consolidation/
├── plan.md              # This file
├── spec.md              # Feature spec (clarified ×3)
├── research.md          # Phase 0 — all unknowns resolved (R1–R14)
├── data-model.md        # Phase 1 — entities & states
├── quickstart.md        # Phase 1 — how to verify each story locally
├── contracts/           # Phase 1 — behavior contracts
│   ├── merged-skill.md
│   ├── prune-on-deploy.md
│   ├── library-prompt.md
│   └── array-guard.md
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
.skillshare/skills/                  # P1: 12 dirs deleted, 2 new survivors added,
│                                    #     5 existing survivors edited (merged content)
configs/claude/scripts/
├── skillclaw_evolve.py              # P1: library prompt descriptions; P3: chunk timeout
├── label_sync.sh                    # P3: argv-passing fix (parse_labels)
├── browser_test.sh                  # P3: argv-passing fixes (×3 sites)
├── (8 user-facing scripts)          # P5: --help + err() sweep
└── test_*.py                        # P3: REMOVED (git mv → tests/python/)
configs/claude/prompts/skillclaw_evolve.md   # P1: library-section wording
bootstrap/lib/common.sh              # P1: deploy_home_skills --delete
docs/
├── COMMANDS.md                      # P2: canonical command table
├── SPEC-SYSTEMS.md                  # P2: NEW — spec/plan systems map
├── SHELL_ANALYSIS_REPORT.md         # P2: archive banner
└── (README/CLAUDE/AGENTS sync)      # P2
CHANGELOG.md                         # P2: Unreleased → dated section
.gitignore                           # P5: records/
.pre-commit-config.yaml              # P3: array-guard local hook
.github/workflows/ci.yml             # P3: array-guard step; P4: pins + caching
tests/
├── lint/check_array_expansion.sh    # P3: NEW guard
├── bats/deploy_skills.bats          # P1: prune cases
├── bats/learning_capture.bats       # P4: NEW
├── bats/check_status.bats           # P4: NEW
├── bats/generate_cursor_rules.bats  # P4: NEW
└── python/test_skillclaw_evolve.py  # P1/P3: library-prompt + timeout cases
```

**Structure Decision**: existing monorepo layout unchanged; only the paths
listed above are touched. One PR per user story (research R14), P1 first;
each PR independently CI-green per the spec's independent-testability
framing.

## Phase summaries

- **Phase 0 (research.md)**: 14 decisions, all spec unknowns resolved with
  file:line evidence — notably: prune = manifest-scoped prune-on-deploy
  (`.deployed-skills` manifest; externally-added skills preserved, with the
  FR-005a safety bounds per contracts/prune-on-deploy.md); evolve timeout 600s
  default; array guard = checker script in pre-commit + CI; 10 (not 3)
  scripts lack `--help`, 8 get it, 2 exempted; cluster math corrected to −12
  (81 → 69).
- **Phase 1 (design)**: data-model.md (skill/cluster/deploy-target/guard
  entities and state transitions), 4 behavior contracts, quickstart.md
  (per-story local verification commands), agent context repointed to this
  plan.
