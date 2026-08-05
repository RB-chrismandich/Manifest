# Implementation Plan: Sub-Agent Dispatch Guidance for Skills

**Branch**: `367-sub-agent-dispatch-guidance` | **Date**: 2026-06-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/367-sub-agent-dispatch-guidance/spec.md`

## Summary

Audit every skill in `.retired skill supply/skills/` and give each a sub-agent **disposition** plus, where it
dispatches, a concrete in-body **trigger**. The existing `tool_policies` block in
`command_config.yml` is the single canonical store: its `parallel_agents` field already governs the
external `parallel_agent.py` harness; this feature adds a parallel `subagents` field (+ optional
`subagent_trigger`) for Claude-native Task sub-agents. The native-vs-external **selection rules**
(including the cross-platform fallback) live once in a referenced location and are linked from
skills, not restated. A canonical fan-out threshold (≥3 independent units, or an existing per-skill
scale threshold) keeps small inputs inline. An automated test wired into CI enforces that every
skill has a disposition and that prose triggers never contradict the config.

**Authoritative skill count**: **88** skill directories (each with a `SKILL.md`). The spec's "89"
counted `.retired skill supply/skills/README.md` in an `ls`. The enforcement test counts skill directories
**dynamically**, so coverage stays correct as skills are added or removed — no number is hardcoded.

**Current gap**: `tool_policies` has 30 entries; **58 skills have no entry** and must be added.

## Technical Context

**Language/Version**: YAML (config), Markdown (skill bodies & docs), Bash (bats test) and/or
Python 3 (pytest) for the enforcement test — matching existing `tests/bats/` + `tests/python/`.

**Primary Dependencies**: `configs/claude/config/command_config.yml` (`tool_policies`), the
orchestration guide `configs/claude/CLAUDE.md`, `.retired skill supply/skills/*/SKILL.md`, `parallel_agent.py`
(referenced, not modified), the Task/Agent tool (Claude-native, referenced).

**Storage**: Files only — config YAML, Markdown skill bodies, a shared reference doc, a test file.

**Testing**: `bats tests/bats/` and `pytest tests/python/`; precedent: `tests/bats/context_budget.bats`.
Lint via `yamllint` (YAML) and `shellcheck` (if bats helpers add shell).

**Target Platform**: Cross-assistant config repo deployed to Claude / Cursor / Gemini / Codex /
Antigravity via the existing symlink/rules deployment model.

**Project Type**: Configuration-as-code repository (no application runtime).

**Performance Goals**: N/A (authoring/config change). Indirect goal: skill guidance must not bloat
auto-loaded context — only `SKILL.md` frontmatter is auto-loaded, so triggers go in bodies and
selection rules are centralized + linked.

**Constraints**: Single source of truth (extend `tool_policies`, no parallel store); no recursive
sub-agent dispatch; respect token-economy (≥3-unit threshold); changes confined to skill bodies, the
shared reference doc, `command_config.yml`, and the test (no change to `parallel_agent.py` or the
Task tool itself).

**Scale/Scope**: 88 skill dispositions (58 new + 30 reconciled), 1 schema extension, 1 shared
selection-rules section, 1 enforcement test, 1 contributor-convention doc.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Configuration-as-Code | **PASS** — all edits land in version-controlled `configs/` and `.retired skill supply/skills/`; deployed via `bootstrap.sh`. No manual edits to `~/.claude/`. |
| II. Parallel Agent Orchestration | **APPLIES** — this is an architecture decision touching the whole skill library. The design itself was cross-verified via `/speckit-clarify` (4 locked decisions); the implementation PR MUST be cross-verified per the Tier-1 gate. The enforcement test additionally codifies the rule. |
| III. Consensus-Driven Decisions | **PASS** — PR review applies the standard consensus thresholds; no bypass. |
| IV. Skill-First Extensibility | **PASS** — no new behavior is absorbed into `parallel_agent.py`; guidance lives in skills + config + a reference doc. The enforcement test is a thin verifier, not a core-engine expansion. |
| V. Bootstrap Reproducibility | **PASS** — config/doc edits deploy idempotently through existing mechanisms; no new install steps. |

**Quality Gates**: Tier-1 (cross-verification, no secrets, error handling, no breaking changes) and
Tier-2 (the new bats/pytest test) both satisfiable. No violations → **Complexity Tracking empty**.

**Gate result**: PASS (no unjustified violations).

## Project Structure

### Documentation (this feature)

```text
specs/367-sub-agent-dispatch-guidance/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — tool_policies schema extension + entities
├── quickstart.md        # Phase 1 output — how to add/decline sub-agent guidance to a skill
├── contracts/           # Phase 1 output
│   ├── tool_policies.subagents.schema.md   # extended-field contract
│   ├── skill-trigger.format.md             # in-body trigger contract
│   └── enforcement-test.contract.md        # what the CI test must assert
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
configs/claude/config/command_config.yml     # EXTEND tool_policies: add `subagents` (+ optional
                                              #   `subagent_trigger`) to every skill; fill 58 missing

configs/claude/references/sub-agent-dispatch.md  # NEW read-on-demand reference: shared "Sub-Agent
                                              #   Selection Rules" (native vs parallel_agent.py +
                                              #   cross-platform fallback) AND the contributor
                                              #   convention (FR-013). Single source skills link to;
                                              #   satisfies SC-007. Kept out of auto-loaded CLAUDE.md
                                              #   for the context budget.

configs/claude/CLAUDE.md                       # ADD ONE pointer line to the "Reference Index"
                                              #   (only ~537 bytes headroom under context_budget.bats).

.retired skill supply/skills/<skill>/SKILL.md            # For "always"/"conditional" skills: ADD a concrete
                                              #   in-body dispatch trigger that links to the shared
                                              #   rules. For "never": one-line rationale.

tests/bats/subagent_policy.bats                # NEW enforcement test (or tests/python/ equivalent):
   OR tests/python/test_subagent_policy.py     #   dynamic coverage + prose↔config consistency
```

**Structure Decision**: No new source tree — this is a config/docs/test change layered onto the
existing repository. The canonical disposition store is the existing `tool_policies` block; the
shared selection rules extend the existing orchestration guide; the enforcement test follows the
`tests/bats/context_budget.bats` precedent.

## Complexity Tracking

> No constitution violations — table intentionally empty.
