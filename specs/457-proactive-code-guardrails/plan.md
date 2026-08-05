# Implementation Plan: Proactive Code Guardrails

**Branch**: `457-proactive-code-guardrails` | **Date**: 2026-07-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/457-proactive-code-guardrails/spec.md`

## Summary

Encode proactive anti-pattern prevention into the toolkit in three layers: (1) seed the existing `knowledge_base.yml` with a curated, research-derived anti-pattern registry (33 entries, 6 categories) carrying detection cues and positive prevention rules; (2) surface write-time guardrails via a compact auto-loaded guidance block plus an on-demand reference, and extend the `code-quality` auto-trigger to flag registry anti-patterns as non-blocking advisory feedback; (3) add one new dedicated `ai-code-audit` skill that runs the seven ordered rubric passes against a target codebase, emits severity-classified evidenced findings aligned with the existing Tier 1/Tier 2 vocabulary, and cross-verifies Critical/High findings before reporting. The existing `antipattern-detect` → `learning_capture.sh` capture loop is extended so newly confirmed anti-patterns feed both prevention and audit without restructuring.

## Technical Context

**Language/Version**: Bash (scripts, bats-tested), Python 3.11 (existing helpers only — no new Python planned), Markdown (skills), YAML (registry/config)

**Primary Dependencies**: `learning_capture.sh` (registry writes), `knowledge_base.yml` (registry store), `code-quality` skill (advisory trigger), `antipattern-detect` skill (capture), `validation_criteria.yml` (severity/tier vocabulary), `generate_cursor_rules.sh` + `generate_commands_doc.py` (derived-guide regeneration)

**Storage**: `configs/claude/config/knowledge_base.yml` (single source of truth for registry entries; deployed to `~/.claude/config/` by bootstrap)

**Testing**: bats (`tests/bats/`) for `learning_capture.sh` schema extensions, registry YAML validity, context budget; existing drift tests (`commands_doc_drift.bats`, `generate_cursor_rules.bats`); seeded-fixture acceptance run for the audit skill; yamllint/shellcheck/markdownlint pre-commit

**Target Platform**: macOS + Linux dev machines (all assistant homes: Claude, Cursor, Gemini, Codex, Antigravity via existing deploy/symlink chain)

**Project Type**: Configuration/skills toolkit (this repo deploys guidance; no application runtime)

**Performance Goals**: Audit of ≤50 source files completes in a single invocation (SC-006); registry lookup adds no measurable session-start cost (summary is static text)

**Constraints**: Auto-loaded guidance MUST keep `context_budget.bats` passing (current cap 22300 chars across skill descriptions; guide additions have their own budget checks). Skills-table token-economy rule: full detail lives in on-demand references, never in Claude auto-loaded guides.

**Scale/Scope**: 33 seeded registry entries across 6 categories (spec floor: ≥25); detection cues for 5 languages (shell, Python, JS/TS, Go, Terraform); 1 new skill; 2 extended skills; 1 new reference doc; larger codebases (>50 files) chunk by top-level directory with per-chunk pass execution and a merged report (research decision R6)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Configuration-as-Code | PASS | All changes land in `configs/claude/config/`, `configs/claude/references/`, and `.retired skill supply/skills/`; deployed via existing bootstrap paths. No manual home-dir edits. |
| II. Parallel Agent Orchestration | PASS | Feature PR will exceed 200 lines and touches security guidance → parallel-agent cross-verification required before merge (planned in tasks). The audit skill itself encodes cross-verification for Critical/High findings (FR-012). |
| III. Consensus-Driven Decisions | PASS | Audit verdict mapping reuses APPROVED/NEEDS_REVIEW/BLOCKED and existing thresholds; no new consensus scheme introduced (FR-006). |
| IV. Skill-First Extensibility | PASS | New capability is a discrete skill (`ai-code-audit`); `parallel_agent.py` and other core scripts are not expanded. `learning_capture.sh` gains only additive optional fields. |
| V. Bootstrap Reproducibility | PASS | No bootstrap changes required — `knowledge_base.yml` and skills are already in the deploy set; changes are content-only and idempotent. |
| VI. State-Gated Lifecycle | ADVISORY WARNING (logged override, since remediated) | Phase 3 (Spec-Review product) was not run before Plan; human-driven work proceeds with this logged override. REMEDIATED 2026-07-01: `/spec-review` panel ran post-tasks (4 rounds, 12 findings dispositioned) and `/speckit-analyze` passed with 0 critical findings. Verify gate: the audit skill is a shipped user-facing workflow → critical-path smoke tests planned (T013/T019/T023). |

**Post-design re-check (after Phase 1)**: PASS — design artifacts introduce no new projects, no core-script expansion, no non-additive schema changes. The Principle VI advisory stands until `/spec-review` runs.

## Project Structure

### Documentation (this feature)

```text
specs/457-proactive-code-guardrails/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── registry-schema.md       # knowledge_base.yml entry contract (extended fields)
│   └── audit-skill-contract.md  # ai-code-audit invocation + report contract
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
configs/claude/
├── config/
│   ├── knowledge_base.yml            # EXTEND: seed 33 registry entries; additive fields
│   ├── command_config.yml            # EXTEND: tool_policies entry for ai-code-audit
│   ├── command_categories.yml        # EXTEND: category entry for ai-code-audit
│   └── validation_criteria.yml       # READ-ONLY: severity/tier vocabulary source
├── references/
│   └── antipatterns.md               # NEW: full prevention-rule detail (on-demand load)
├── scripts/
│   └── learning_capture.sh           # EXTEND: accept optional severity/detection_cue/
│                                     #   prevention_rule/provenance + guardrail-category
│                                     #   tag (additive)
└── CLAUDE.md                         # EXTEND: compact guardrails summary (budget-checked)

configs/gemini/GEMINI.md              # EXTEND: mirrored guardrails digest
configs/cursor/rules/orchestration.mdc # EXTEND: mirrored guardrails digest
AGENTS.md                             # EXTEND: mirrored digest (codex target via configs/codex symlink)

.retired skill supply/skills/
├── ai-code-audit/SKILL.md            # NEW: seven-pass audit skill
├── code-quality/SKILL.md             # EXTEND: consult registry; advisory anti-pattern flags
└── antipattern-detect/SKILL.md       # EXTEND: capture writes new optional fields

tests/
├── bats/
│   ├── learning_capture.bats         # EXTEND: new-field round-trip tests
│   ├── knowledge_base_registry.bats  # NEW: seeded-registry schema/coverage assertions
│   └── context_budget.bats           # GUARD: must keep passing (adjust only if justified)
└── fixtures/audit-seeded/            # NEW: small fixture codebase with planted anti-patterns
```

**Structure Decision**: Single-repo configuration toolkit. All new behavior lands as skill markdown + YAML content + one reference doc; the only script change is additive field support in `learning_capture.sh`. Derived artifacts (cursor `.mdc` rules, `docs/COMMANDS.md`, Gemini/Codex/Antigravity guides) are regenerated, never hand-edited.

## Complexity Tracking

> No Constitution Check violations requiring justification. (The Principle VI item is a logged
> advisory override for phase ordering, not a design violation; remediation is scheduled —
> run `/spec-review` before `/speckit-tasks`.)

| Budget change | Why Needed | Simpler Alternative Rejected Because |
|---------------|------------|--------------------------------------|
| Skill-frontmatter cap 22600 → 22800 (context_budget.bats) | `ai-code-audit` is a genuinely-new entry-point skill; its description is always-loaded trigger text with no read-on-demand alternative | Trim-first was done (3 skills trimmed ~190 chars, new description cut to ~300); the residual still exceeded the cap. Folding into an existing skill would violate the clarified "dedicated audit skill" decision |
