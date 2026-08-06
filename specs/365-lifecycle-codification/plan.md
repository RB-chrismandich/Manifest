# Implementation Plan: Codified State-Gated Development Lifecycle

**Branch**: `365-lifecycle-codification` | **Date**: 2026-06-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/365-lifecycle-codification/spec.md`

## Summary

Codify the repo's nine-phase development lifecycle (Specify→Clarify→Spec-Review[product]→Plan→Task Creation→Analyze→Spec-Review[technical]→Implement→Verify) as governed, state-gated process. The technical approach (research.md): a shared, bats-tested Bash state machine `configs/claude/scripts/lifecycle.sh` with a **pure `decide` core** (fail-closed, always exit 0) plus stateful subcommands, fronted by a thin `/lifecycle` skill and consumed by the autodev loop for hard enforcement — mirroring the 360/361 `merge_decision.sh`/`verification_gate.sh` idiom. The Verify phase consumes the existing smoke orchestrator as-is (`smoke_test.py run --tier Lite`, exit 0/1/2). Work is tracked in a four-tier hierarchy (Initiative→Epic→Task→Sub-Task) abstracted over GitHub/GitLab/Linear (existing tooling) and Jira (pre-auth Atlassian MCP). The rules are codified in the constitution (new Principle VI + "Development Lifecycle" section, MINOR bump v1.1.0) with provider specifics in config.

## Technical Context

**Language/Version**: Bash (macOS bash 3.2+ / Linux) with embedded `python3 -c` heredocs for JSON/decision logic (the repo's decide-core idiom). Python 3.11 only inside the consumed smoke runtime — not re-implemented here.

**Primary Dependencies**: smoke orchestrator (`smoke_test.py`) · `git_ops.sh`/`git_platform.sh`/`linear_ops.sh` · `parallel_agent.py` · `spec_review.sh` (extended with `--mode`) · Atlassian MCP (Jira) · `labels.yml`/`label_sync.sh` · the `/speckit-*` and `/spec-review` skills (phase executors).

**Storage**: per-track JSON under `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/lifecycle/state/<provider>__<entity-id>.json` (`0700`/`0600`, atomic, secret-redacted — smoke `StateManager` pattern); coarse status mirrored to tracker labels (GH/GL/Linear) or Jira transitions.

**Testing**: `bats tests/bats/lifecycle.bats` (decide core + subcommands; the safety contract) and `tests/bats/spec_review_mode.bats`; `shellcheck` + `yamllint` lint; smoke catalog exercised via the orchestrator's own suite. pytest only if Python helpers grow beyond heredocs.

**Target Platform**: developer machines + CI (macOS/Linux), deployed via `bootstrap.sh` to `~/.claude/`.

**Project Type**: CLI/automation tooling within the Manifest configuration repo (single project; shell-first).

**Performance Goals**: `decide`/`gate` resolves sub-second (pure function, no I/O); Verify latency bounded by the smoke run (`Lite` < 2 min per SC-003).

**Constraints**: bash 3.2 compatibility; gating **fails closed**; no secrets in logs/state/reports (FR-025); consume the smoke runtime unchanged (FR-012); Jira via pre-auth MCP only (FR-020); `--help` succeeds before any dependency lookup; errors via `err()` (repo Script Conventions).

**Scale/Scope**: one new script (`lifecycle.sh`) + one skill (`/lifecycle`) + one provider config + a `--mode` flag on `spec_review.sh` + a constitution amendment, spanning 4 providers and 9 phases.

## Constitution Check

*GATE: evaluated against `.specify/memory/constitution.md` v1.0.0 before Phase 0 and re-checked post-design.*

| Principle | Status | Notes |
|---|---|---|
| I. Configuration-as-Code | ✅ PASS | All artifacts in `configs/` + `.retired skill supply/skills/`; deployed via `bootstrap.sh`. Requires redeploy (noted as a task). No manual edits to `~/.claude/`. |
| II. Parallel Agent Orchestration | ✅ PASS | `lifecycle.sh` is safety-gate logic (>200 lines, security-adjacent) → cross-verified via the spec-review panel + `parallel_agent.py` before merge (already exercised in this feature's own lifecycle). |
| III. Consensus-Driven Decisions | ✅ PASS | Review/analyze gates reuse the APPROVED/NEEDS_REVIEW/BLOCKED + ≥80% consensus model (FR-027); no new thresholds invented. |
| IV. Skill-First Extensibility | ✅ PASS | User-facing capability is the `/lifecycle` skill delegating to a discrete testable helper — not an expansion of `parallel_agent.py` (the 361 precedent). |
| V. Bootstrap Reproducibility | ✅ PASS | `init` guarded (idempotent per track); all provider writes idempotent (FR-022); fail-closed on error. |

**Governance action**: this feature also **amends** the constitution (adds Principle VI + "Development Lifecycle" section, MINOR → v1.1.0) via `/speckit-constitution`. That is an in-scope, policy-compliant amendment (additions only, no removals/redefinitions) — not a violation.

**Result: PASS — no violations; Complexity Tracking not required.**

## Project Structure

### Documentation (this feature)

```text
specs/365-lifecycle-codification/
├── plan.md              # this file
├── research.md          # Phase 0 (7 decisions D1–D7)
├── data-model.md        # Phase 1 (7 entities)
├── quickstart.md        # Phase 1 (end-to-end usage)
├── contracts/           # Phase 1
│   ├── lifecycle-cli.md          # lifecycle.sh subcommands + decide JSON I/O
│   ├── provider-mapping.md       # tier map, status map, reconciliation, entry detection
│   └── verify-and-specreview.md  # smoke Verify gate + spec_review --mode
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
configs/claude/
├── scripts/
│   ├── lifecycle.sh                 # NEW — shared state machine (decide core + init/status/advance/anchor/regress)
│   ├── spec_review.sh               # MODIFIED — add --mode product|technical (env-seam sugar)
│   ├── git_ops.sh / git_platform.sh # REUSED — GitHub/GitLab + entry-point detection (extended for jira/linear)
│   ├── linear_ops.sh                # REUSED — Linear hierarchy (parentId/sub-issues)
│   ├── smoke_test.py                # REUSED AS-IS — Verify gate runtime
│   └── parallel_agent.py            # REUSED — consensus dimension for review gates
├── config/
│   ├── lifecycle_providers.yml      # NEW — tier→construct map, canonical-status map, missing-tier behavior, access
│   ├── labels.yml                   # REUSED — canonical status labels
│   └── mcp_servers.yml              # REUSED — atlassian (Jira) MCP; wire into settings.local.json
└── settings.local.json             # MODIFIED — register atlassian MCP server

.retired skill supply/skills/lifecycle/SKILL.md   # NEW — /lifecycle (thin front-end; phase→command mapping, human/agent)

.specify/memory/constitution.md          # MODIFIED — Principle VI + "Development Lifecycle" section, v1.1.0
.specify/templates/{plan,tasks}-template.md  # MODIFIED — Constitution Check + smoke-coverage task category
docs/SPEC-SYSTEMS.md                     # MODIFIED — describe the 9-phase state-gated lifecycle

tests/bats/
├── lifecycle.bats                   # NEW — decide core (skip/gate/fail-closed) + subcommand state
└── spec_review_mode.bats            # NEW — --mode flag back-compat + template/state routing

# Autodev enforcement host (separate wiring task; see 361)
configs/claude/scripts/{auto_issue_dev.sh,pr_merge_loop.sh}  # MODIFIED — call lifecycle.sh gate before advance/merge
```

**Structure Decision**: Single-project, shell-first, matching the repo's existing `configs/claude/scripts/` automation layer. The orchestrator is a shared script (one tested gate) consumed by both the `/lifecycle` skill (humans) and the autodev loop (agents), with provider specifics in `config/` and governance in the constitution — keeping each concern at its established altitude.

## Complexity Tracking

*No constitution violations — not required.*
