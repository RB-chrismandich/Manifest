# Implementation Plan: Command Discovery & Workflow Guidance

**Branch**: `362-command-help-hints` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/362-command-help-hints/spec.md`

## Summary

Surface the repository's ~84 commands so the right one is findable and the intended
workflow is learnable, without managing the commands themselves (read-only guidance).
Three capabilities, shipped in priority order: (P1) a categorized, searchable **discovery**
surface in two forms — an interactive in-session command and a generated, drift-free
`docs/COMMANDS.md` — both built from one source (`SKILL.md` frontmatter); (P2) **event-driven,
one-shot workflow hints** at recognized moments (pre-commit, PR open, refactor start, high
context); (P3) **tunable best-practice reminders** with global + per-category opt-out and a
verbosity level. All five agent platforms reach parity in v1 via their existing adapter
conventions. Technical approach: a Python catalog **generator** over the skill source of
truth, a new discovery **skill**, a cross-platform **hint/reminder registry** delivered
through the existing `ai-hooks-integration` hook plumbing, and a **drift-check** wired into CI.

## Technical Context

**Language/Version**: Python 3.9+ (3.12+ preferred, per repo); Bash 4+; Markdown/YAML. No new languages.

**Primary Dependencies**: `pyyaml` (already used) for frontmatter parsing; existing repo tooling — `generate_cursor_rules.sh` (Cursor `.mdc` generation pattern), `bootstrap.sh` deploy, `ai-hooks-integration` skill (cross-tool lifecycle hooks). No new runtime dependency.

**Storage**: Files only. Source of truth = `.skillshare/skills/*/SKILL.md` frontmatter. Generated artifacts = `docs/COMMANDS.md` + an intermediate machine catalog. Hint registry + **shipped** guidance defaults = committed YAML under `configs/claude/config/`. **User preference overrides** = a gitignored `~/.claude/config/guidance_local.yml` (so a single opt-out toggle never dirties the tracked tree — SC-004); effective prefs = shipped defaults ← user-local override (local wins). Rate-limit state = small local state file under the agent home (not committed).

**Testing**: `pytest` (generator, catalog, derivation, drift-check); `bats` (CLI `--help`, drift-check exit codes, hook firing, context-budget guard).

**Target Platform**: Developer workstations (macOS Intel/Apple Silicon, Linux) running one or more of the 5 agent CLIs/IDEs.

**Project Type**: CLI / configuration tooling (single project; existing repo layout).

**Performance Goals**: Discovery returns within the first screen / under 30s of human time (SC-001); full catalog generation over ~84 skills completes in a few seconds; hint selection adds negligible per-event latency.

**Constraints**: Token economy is a hard gate — any always-loaded catalog content injected into agent guides MUST pass the existing `context_budget` check (FR-009, SC-006); hints are one-shot, never persisted into always-loaded context; no new external services; generation idempotent (Constitution V).

**Scale/Scope**: ~84 commands today and growing; 5 platforms; an initial handful of workflow moments (commit, PR open, refactor start, high context); one curated category taxonomy.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Configuration-as-Code | ✅ PASS | All artifacts live in `configs/` + `.skillshare/`; `docs/COMMANDS.md` is **generated** (never hand-edited) and deployed reproducibly. Drift-check enforces no manual edits. |
| II. Parallel Agent Orchestration | ✅ PASS (process gate) | Change will exceed 200 lines across generator + skill + hooks → MUST be cross-verified by ≥2 parallel agents before merge (`parallel_agent.py`). Recorded as a PR-time gate, not a design violation. |
| III. Consensus-Driven Decisions | ✅ PASS | Applies at review; thresholds unchanged. |
| IV. Skill-First Extensibility | ✅ PASS | Discovery is a new **skill**; hints/reminders ride hooks + a registry. `parallel_agent.py` and other core scripts are NOT expanded to absorb this. The generator is a discrete support script, not core-engine growth. |
| V. Bootstrap Reproducibility | ✅ PASS | Generator + deployment are idempotent and guarded; non-zero exit on unrecoverable failure. |

**Result**: No violations. Complexity Tracking table intentionally left empty.

## Project Structure

### Documentation (this feature)

```text
specs/362-command-help-hints/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (CLI + schema contracts)
│   ├── discovery-command.md
│   ├── generator-cli.md
│   ├── catalog-schema.md
│   ├── hint-registry-schema.md
│   └── guidance-prefs-schema.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
.skillshare/skills/
├── help/                              # NEW — interactive discovery skill (/help)
│   └── SKILL.md
└── <existing skills>/SKILL.md         # source of truth; optional `category:` frontmatter added incrementally

configs/claude/
├── scripts/
│   ├── command_catalog.py             # NEW — parse SKILL.md frontmatter → machine catalog; derive when-to-use; resolve availability
│   ├── generate_commands_doc.py       # NEW — render catalog → docs/COMMANDS.md; --check = drift-only (CI-enforced via T014; local save-hook optional, not in v1 scope)
│   ├── guidance_hint.py               # NEW — map Workflow Moment → command(s); one-shot hint emitter w/ rate-limit + prefs
│   └── generate_cursor_rules.sh       # EXTENDED — also emit the discovery rule for Cursor
├── config/
│   ├── command_categories.yml         # NEW — defines the VALID taxonomy (keys/labels/order) + an explicit overrides map; per-skill `category:` frontmatter is authoritative for assignment, overrides win only where present
│   ├── hint_registry.yml              # NEW — Workflow Moment → command(s) mapping, with priority/dedup keys
│   └── guidance.yml                   # NEW — SHIPPED guidance defaults (committed)

# user preference override (NOT in repo; gitignored, created on first toggle):
#   ~/.claude/config/guidance_local.yml  — effective prefs = guidance.yml ← guidance_local.yml (local wins)

docs/COMMANDS.md                       # GENERATED reference doc (committed; regenerated, drift-checked)

configs/gemini/GEMINI.md               # EXTENDED — generated catalog table injected (token-budget bounded)
configs/codex/AGENTS.md (via AGENTS.md)# EXTENDED — same generated catalog table
configs/antigravity/                   # parity via existing symlinks to ../claude

tests/
├── python/command_help/
│   ├── test_command_catalog.py        # frontmatter parse, when-to-use derivation, availability resolution
│   ├── test_generate_commands_doc.py  # rendering + --check drift detection
│   └── test_guidance_hint.py          # moment→command mapping, rate-limit, opt-out, verbosity
└── bats/
    ├── command_help_cli.bats          # /help --help path, search, grouping, unavailable marking
    ├── commands_doc_drift.bats         # drift-check exit codes (clean vs dirty)
    └── guidance_hint_hook.bats         # hook fires one-shot at a moment; suppressed when opted out
```

**Structure Decision**: Single-project, follows the existing repo layout — scripts in `configs/claude/scripts/`, config in `configs/claude/config/`, the new discovery surface as a skill in `.skillshare/skills/help/`, generated reference in `docs/COMMANDS.md`, and per-platform reach via the established adapter conventions (`generate_cursor_rules.sh` for Cursor, guide injection for Gemini/Codex, symlinks for Antigravity). No new top-level directories; tests split across `pytest` and `bats` per repo convention.

## Cross-Platform Delivery & Bounding

### Capability matrix (FR-011 — gaps documented, not dropped)

`ai-hooks-integration` provides an event-hook substrate for Claude Code, Gemini CLI, and
Cursor — but **not** Codex or Antigravity. Per FR-011, the gap is documented here with a
fallback rather than silently dropped.

| Platform | Discovery (list/search) | Event-driven hints | Reminders |
|----------|-------------------------|--------------------|-----------|
| Claude Code | `/help` skill | hooks (`PreToolUse` etc.) | hooks |
| Cursor | generated `.mdc` rule + `docs/COMMANDS.md` | `ai-hooks-integration` | `ai-hooks-integration` |
| Gemini CLI | `/help` skill (shared) + compact guide index | `ai-hooks-integration` | `ai-hooks-integration` |
| Codex | `/help` skill (shared) + compact guide index | **GAP** — no hook substrate → fallback: standing reminder line in `AGENTS.md` (budget-bounded) | standing line fallback |
| Antigravity | `/help` skill (shared, via symlink) + compact guide index | **GAP** — same fallback as Codex | standing line fallback |

**Discovery parity note**: the `/help` skill in `.skillshare/skills/help/` deploys to every
platform via the existing skill-symlink chain, so full one-line descriptions (FR-001) are
available everywhere through `/help`. The always-loaded guide index is deliberately
description-less (FR-009) and links back to `/help` for detail — so FR-001 is met by the
skill, FR-009 by the bounded index. Hint/reminder delivery is the only column with a
documented Codex/Antigravity gap.

**Documented gap**: Codex and Antigravity reach full **discovery** parity but lack
event-driven, per-moment hints. They fall back to a single standing reminder line in their
always-loaded guide (bounded by `context_budget`). Closing the gap fully depends on those
CLIs gaining a hook API; tracked as a known limitation, not a v1 blocker.

### Always-loaded injection bounding (FR-009 / SC-006 / Edge "context-budget pressure")

Guides (`GEMINI.md`, `AGENTS.md`, Cursor rule) receive **only a compact index** — category
headers + `` `/name` `` links, **no descriptions** — capped at a hard line count with a
`Run /help for full details` fallback. Full descriptions/when-to-use live only in the
on-demand `/help` surface and the (non-always-loaded) `docs/COMMANDS.md`. A `bats` test
asserts the injected block stays under the `context_budget` threshold as the catalog grows.

## Complexity Tracking

> No Constitution Check violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
