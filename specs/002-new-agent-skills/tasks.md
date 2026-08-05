---
description: "Task list for 002-new-agent-skills implementation"
---

# Tasks: New Agent Skills (Version Pinning, Docs Orchestration, PR Review, Branch Cleanup)

**Input**: Design documents from `/specs/002-new-agent-skills/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the Manifest constitution mandates `bats tests/bats/` for shell changes and `shellcheck`/`yamllint` lint gates, so shell-helper test tasks are first-class here.

**Organization**: Tasks are grouped by user story. US1 (version-pin, P1) is the MVP. US2–US4 are independent of each other once Phase 2 completes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1=version-pin, US2=docs-all, US3=pr-review, US4=branch-clean
- All paths are repo-relative from the worktree root.

## Path Conventions

Agent-configuration repo (single project): skills in `.retired skill supply/skills/<name>/SKILL.md`
(source of truth; `configs/claude/skills` is a symlink), helper scripts in
`configs/claude/scripts/`, config in `configs/claude/config/`, tests in `tests/bats/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the skill directories and confirm the deploy/test harness covers them.

- [x] T001 [P] Create skill directories with placeholder SKILL.md frontmatter in `.retired skill supply/skills/version-pin/SKILL.md`, `.retired skill supply/skills/docs-all/SKILL.md`, `.retired skill supply/skills/pr-review/SKILL.md`, `.retired skill supply/skills/branch-clean/SKILL.md`
- [x] T002 [P] Verify `bootstrap.sh` `deploy_home_skills` globs the new directories (symlink-safe) and that `configs/claude/skills` remains a symlink — record finding in `specs/002-new-agent-skills/quickstart.md` if any change is needed

**Checkpoint**: Four discoverable (empty) skills exist and deploy without breaking the symlink.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Register all four skills in the shared config + doc files in one pass so the
per-story phases (which create different files) can proceed in parallel without contending
on these shared files.

- [x] T003 Add `tool_policies` entries for all four skills to `configs/claude/config/command_config.yml` per research §R8 (version-pin: Read/Glob/Grep/Bash/Edit/Write, Tier 1; docs-all: Read/Glob/Grep/Agent, Tier 2; pr-review: Read/Glob/Grep/Bash, Tier 2; branch-clean: Read/Glob/Grep/Bash, Tier 1 on apply), AND add the `version_pin` rule-set block (globs, ecosystem, resolve_cmd, hash, bypass marker) per data-model §2
- [x] T004 Add `command_overrides` entries for all four skills to `configs/claude/config/validation_criteria.yml` (version-pin Tier 1; branch-clean Tier 1 destructive path; docs-all + pr-review Tier 2 maintainability) — mirrors existing override blocks
- [x] T005 [P] Add the four skills to the command/skill tables in `CLAUDE.md`, `configs/claude/CLAUDE.md`, and `docs/COMMANDS.md` consistent with existing entries (FR-023)
- [x] T006 Validate config parses after edits: `python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"` and the same for `validation_criteria.yml`, plus `yamllint` both files

**Checkpoint**: All four skills are registered and config still parses + lints. Stories can now proceed independently.

---

## Phase 3: User Story 1 — Enforce Version Pinning (Priority: P1) 🎯 MVP

**Goal**: Detect loose dependency references, resolve specific versions + integrity hashes
via native tooling, auto-fix on demand, warn-only on the save hook, with explicit bypass.

**Independent Test**: Run against a fixture `requirements.txt` (`requests` unpinned) and
`docker-compose.yaml` (`postgres:latest`); confirm on-demand run rewrites to specific
version + hash, `--check` reports without editing, compliant/bypassed lines untouched, and
a second run is a no-op.

- [x] T007 [P] [US1] Write `tests/bats/version_pin.bats` covering: loose-detection per ecosystem, on-demand rewrite to version+hash, `--check` makes no edits + non-zero exit, compliant left unchanged, `# version-pin:ignore` bypass preserved, unresolved/offline → warning + untouched, idempotent second run, AND hook-scoping — a recognized file (e.g. `requirements.txt`) IS processed while an unrelated file (e.g. `README.md`) is NOT (the negative case of SC-003) (SC-001/SC-002/SC-003, contract `version-pin.md`)
- [x] T008 [US1] Implement `configs/claude/scripts/version_pin.sh`: read `version_pin` rule set from `command_config.yml`; parse Dependency References (data-model §1); classify compliant/violation/bypassed/unresolved; resolve via native tools (pip/pip-compile, `docker manifest`, npm, `git ls-remote` for GHA) per research §R1; on-demand rewrite vs `--check` warn-only per §R2; emit the contract output schema + exit codes
- [x] T009 [US1] Author `.retired skill supply/skills/version-pin/SKILL.md` (name/description frontmatter; workflow: invoke `version_pin.sh`, present results, apply/confirm; document flags from contract; document non-fatal failure handling FR-007)
- [x] T010 [US1] Register the warn-only save-hook as a `PostToolUse` entry (matcher `Write|Edit`) in `configs/claude/settings.local.json` that calls `version_pin.sh --check "$file_path"`; the script — not the matcher — enforces the recognized-glob scoping (so non-tracked files no-op, per T007). Make the insertion idempotent (skip if an equivalent entry already exists) per Constitution V, and mirror the cross-tool wiring via `ai-hooks-integration` conventions. Document the recipe in the SKILL.md and `specs/002-new-agent-skills/quickstart.md`
- [x] T011 [US1] Run `shellcheck configs/claude/scripts/version_pin.sh` and `bats tests/bats/version_pin.bats`; fix to green

**Checkpoint**: `/version-pin` is a complete, independently shippable MVP.

---

## Phase 4: User Story 2 — All-in-One Documentation Refresh (Priority: P2)

**Goal**: Orchestrate `docs-readme` / `docs-diagrams` / `docs-improve` as sub-agents,
choosing order per run with a documented default fallback, into one consolidated report.

**Independent Test**: Run `/docs-all`; confirm all three sub-skills dispatch as sub-agents,
the report states the order + rationale + per-sub-skill outcome, and a forced sub-skill
failure does not abort the others.

- [x] T012 [US2] Author `.retired skill supply/skills/docs-all/SKILL.md`: dispatch the three docs skills via the Agent tool; per-run ordering from changed-file signals with default precedence `readme → diagrams → improve` and `docs-improve` always last (research §R7); continue-on-failure; emit the consolidated Docs Run Report (data-model §5, contract `docs-all.md`)
- [x] T013 [US2] Add a manual verification scenario to `specs/002-new-agent-skills/quickstart.md` confirming order/rationale/failure-surfacing behavior (no script ⇒ no bats; orchestration is exercised manually)

**Checkpoint**: `/docs-all` delivers a one-command docs refresh.

---

## Phase 5: User Story 3 — Review All Open Pull Requests (Priority: P2)

**Goal**: Enumerate all open PRs via the existing platform abstraction and recommend a
disposition per PR, analysis-only by default.

**Independent Test**: Run `/pr-review` against a repo with multiple open PRs; confirm one
row per PR with mergeability/checks/staleness + disposition + rationale, zero mutations,
and clean empty-queue / unauthenticated handling.

- [x] T014 [P] [US3] Write `tests/bats/pr_review.bats` covering: enumeration via mocked `git_ops.sh pr-list`, disposition heuristic (merged/superseded→close, conflicting/failing→needs-rebase, clean+passing→merge, else keep), empty-queue clean output, unauthenticated distinct message, analysis-only (no mutating calls) (contract `pr-review.md`, data-model §3)
- [x] T015 [US3] Implement `configs/claude/scripts/pr_review.sh`: detect platform via `git_platform.sh`; enumerate via `git_ops.sh pr-list` and enrich with `pr-view`/`pr-diff`/`pr-checks`; compute PR Assessment fields + disposition; support `--stale-days`, `--platform`, `--json`; never call mutating subcommands (research §R5)
- [x] T016 [US3] Author `.retired skill supply/skills/pr-review/SKILL.md` (frontmatter; invoke `pr_review.sh`; present prioritized table; explicit analysis-only contract FR-014)
- [x] T017 [US3] Run `shellcheck configs/claude/scripts/pr_review.sh` and `bats tests/bats/pr_review.bats`; fix to green

**Checkpoint**: `/pr-review` triages the open-PR queue read-only.

---

## Phase 6: User Story 4 — Clean Up Stale Branches (Priority: P3)

**Goal**: Identify merged / `[gone]` / stale branch candidates, dry-run by default,
local-only deletion with remote opt-in, never touching protected/current branches.

**Independent Test**: In a repo with a merged branch, a `[gone]` branch, and a protected
branch, confirm the first two are listed (grouped by reason), the protected/current are
never listed, dry-run deletes nothing, and `--apply` deletes only confirmed branches.

- [x] T018 [P] [US4] Write `tests/bats/branch_clean.bats` covering: candidate grouping (merged/gone/stale), protected + current-HEAD exclusion, unmerged never in `merged` category, dry-run default deletes nothing, `--apply` deletes + reports outcomes incl. failures, local-only default vs `--include-remote` (contract `branch-clean.md`, data-model §4)
- [x] T019 [US4] Implement `configs/claude/scripts/branch_clean.sh`: classify via `git branch --merged`, `git for-each-ref ... upstream:track [gone]`, last-commit-date staleness; read protected globs + `--stale-days` from `command_config.yml` `branch_clean` block; dry-run default, `--apply` + confirmation, `--include-remote` opt-in via `git_platform.sh`; report each outcome (research §R6)
- [x] T020 [US4] Add the `branch_clean` config block (protected globs, default stale-days) to `configs/claude/config/command_config.yml`
- [x] T021 [US4] Author `.retired skill supply/skills/branch-clean/SKILL.md` (frontmatter; invoke `branch_clean.sh`; present grouped candidates; safety/confirmation contract FR-017/FR-018/FR-020)
- [x] T022 [US4] Run `shellcheck configs/claude/scripts/branch_clean.sh` and `bats tests/bats/branch_clean.bats`; fix to green

**Checkpoint**: `/branch-clean` prunes branches safely.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Repo-wide gates and final consistency.

- [x] T023 [P] Run full lint sweep: `shellcheck configs/claude/scripts/version_pin.sh configs/claude/scripts/pr_review.sh configs/claude/scripts/branch_clean.sh` and `yamllint configs/claude/config/*.yml`
- [x] T024 [P] Run full test suite: `bats tests/bats/` (all new + existing) to confirm no regressions
- [x] T025 [P] Deploy check: `./bootstrap.sh` then confirm `ls ~/.claude/skills | grep -E 'version-pin|docs-all|pr-review|branch-clean'` lists all four (Constitution V idempotency: re-run is a no-op). *Verified 2026-06-11*: all four present in `.retired skill supply/skills/` and deployed in `~/.claude/skills/`
- [x] T026 Final docs consistency pass: ensure CLAUDE.md / configs/claude/CLAUDE.md / docs/COMMANDS.md tables, `Available Commands`, and `Adding New Skills` references are consistent across all four skills
- [x] T027 [P] Constitution Principle II gate — cross-verify the security-sensitive shell helpers with parallel agents before merge: `~/.claude/scripts/parallel_agent.py --json --timeout 600 --review <abs-path>/configs/claude/scripts/version_pin.sh` and the same for `branch_clean.sh` (its destructive `--apply` path). Resolve any ≥HIGH consensus findings; record the consensus verdict in the PR description. *Closed 2026-06-11*: equivalent gate applied retroactively during specs/003 — version_pin.sh and branch_clean.sh were hardened (US3, PR #293) and independently reviewed by Copilot + Gemini CLI + an isolated Claude reviewer across PRs #289-#294 (parallel_agent.py SDK backends unavailable on this machine)

---

## Dependencies & Execution Order

```text
Phase 1 (Setup: T001–T002)
        ↓
Phase 2 (Foundational: T003 → T004 → T006; T005 [P]) ── blocks all stories (shared config/docs)
        ↓
   ┌────────────┬────────────┬────────────┐
Phase 3 US1   Phase 4 US2   Phase 5 US3   Phase 6 US4   ← independent, can run in parallel
(T007–T011)   (T012–T013)   (T014–T017)   (T018–T022)
   └────────────┴────────────┴────────────┘
        ↓
Phase 7 (Polish: T023–T027)
```

- **Within a story**: the `.bats` test [P] is authored alongside; the helper script depends on the rule-set/config from Phase 2; SKILL.md can be written in parallel with its script (different files); the per-story lint+test task runs last.
- **US4 note**: T020 edits the shared `command_config.yml` again — run it without `[P]` against other Phase-2/other-story config edits to avoid a write conflict.
- **Cross-story parallelism**: US1–US4 touch disjoint scripts, skill dirs, and bats files, so the four story phases are mutually parallelizable after Phase 2.

## Parallel Execution Examples

- **Phase 1**: T001 and T002 together.
- **After Phase 2**: launch one agent per story — `T007/T009/T010` (US1), `T012` (US2), `T014/T016` (US3), `T018/T021` (US4) can start in parallel; each story's script + lint task follows its own test.
- **Phase 7**: T023, T024, T025, T027 together (read-only / independent gates); T026 (docs consistency) after the others.

## Implementation Strategy

- **MVP = User Story 1 (`version-pin`)** — the P1, security-critical, supply-chain skill. Ship it first and independently; it delivers value alone.
- **Incremental delivery**: After the MVP, US2/US3/US4 can be delivered in any order (all P2/P3, all independent). Recommended order matches priority: docs-all → pr-review → branch-clean.
- **Each story is independently testable** via its checkpoint criteria before moving on.

## Task Summary

- **Total tasks**: 27
- **By story**: Setup 2 · Foundational 4 · US1 5 · US2 2 · US3 4 · US4 5 · Polish 5
- **Parallel opportunities**: Phase 1 (2), the four story phases run concurrently after Phase 2, Phase 7 gates (T023/T024/T025/T027); plus per-story test/skill authoring.
- **Suggested MVP scope**: Phases 1–2 + Phase 3 (US1 `version-pin`).
