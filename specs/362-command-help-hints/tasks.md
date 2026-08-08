---

description: "Task list for Command Discovery & Workflow Guidance"
---

# Tasks: Command Discovery & Workflow Guidance

**Input**: Design documents from `specs/362-command-help-hints/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: INCLUDED — the Manifest constitution requires `pytest` (Python) and `bats` (shell) coverage, and plan.md enumerates test files. Test tasks are written before their implementation and must FAIL first.

**Organization**: Tasks grouped by user story (P1→P3) for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (setup, foundational, polish carry no story label)

## Path Conventions

Single project on the existing repo layout: scripts in `configs/claude/scripts/`, config in `configs/claude/config/`, the discovery skill in `.retired skill supply/skills/help/`, generated reference at `docs/COMMANDS.md`, tests in `tests/python/command_help/` and `tests/bats/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding and the curated taxonomy that downstream work reads.

- [X] T001 Create the curated taxonomy config `configs/claude/config/command_categories.yml` with keys/labels/order (`git-pr, docs, security, planning, skills, ci-cd, infra, meta`) plus an empty `overrides:` map (per research D1)
- [X] T002 [P] Create the discovery skill scaffold `.retired skill supply/skills/help/SKILL.md` with `name`/`description` frontmatter (description using the "Use when…" convention)
- [X] T003 [P] Create test scaffolds: `tests/python/command_help/__init__.py` and empty `tests/bats/command_help_cli.bats`, `tests/bats/commands_doc_drift.bats`, `tests/bats/guidance_hint_hook.bats`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The command catalog is the backbone every user story reads from.

**⚠️ CRITICAL**: No user story work can begin until the catalog exists.

- [X] T004 [P] Write `tests/python/command_help/test_command_catalog.py` FIRST (frontmatter parse with symlink-following, `when_to_use` derivation per D2, category precedence per D1, availability resolution per D6, duplicate/empty-skill errors) — must FAIL
- [X] T005 Implement `configs/claude/scripts/command_catalog.py` — parse `.retired skill supply/skills/*/SKILL.md`, derive `when_to_use`, resolve `category` (frontmatter > overrides map > uncategorized), compute `availability` (services.yml + per-platform deployment), emit machine catalog per `contracts/catalog-schema.md`; `--json`, `--platform`, and `--help`-before-deps
- [X] T006 Make T004 pass; add the `--help` path test to `tests/bats/command_help_cli.bats`

**Checkpoint**: Catalog parses the real ~84 skills deterministically — stories can begin.

---

## Phase 3: User Story 1 - Find the right command fast (Priority: P1) 🎯 MVP

**Goal**: Two discovery surfaces (interactive `/help` + generated `docs/COMMANDS.md`) listing every command with category + when-to-use, searchable, drift-free, marking unavailable commands.

**Independent Test**: Run `/help branches` → `branch-clean`/`repo-hygiene` surface; listing matches installed skills; add a skill → `generate_commands_doc.py --check` fails until regenerated.

### Tests for User Story 1 ⚠️ (write first, must FAIL)

- [X] T007 [P] [US1] `tests/python/command_help/test_generate_commands_doc.py` — render correctness + `--check` drift detection (clean=0, drift=1)
- [X] T008 [P] [US1] `tests/bats/commands_doc_drift.bats` — drift-check exit codes against a fixture skill add/remove
- [X] T009 [P] [US1] Extend `tests/bats/command_help_cli.bats` — search ranking, category grouping, unavailable marking, no-match message, and the truncation/`--limit` path (default cap + "N more" footer)

### Implementation for User Story 1

- [X] T010 [US1] Implement discovery query/format in `configs/claude/scripts/command_catalog.py` (or a `discovery` function module) — weighted search ranking per D7, grouped output, availability marking, `--all`, and **a default row cap with `--limit <N>` override** emitting a `… N more — narrow with /help <query>` footer when truncated (spec "context-budget pressure" edge case) (depends on T005)
- [X] T011 [US1] Implement `configs/claude/scripts/generate_commands_doc.py` — render catalog → `docs/COMMANDS.md`; `--check` drift mode (exit 0/1/2); compact-index mode for guide injection (depends on T005)
- [X] T012 [US1] Author `.retired skill supply/skills/help/SKILL.md` behavior — invoke discovery with `query`/`--category`/`--all` per `contracts/discovery-command.md`; `--help` before any load
- [X] T013 [US1] Generate the initial `docs/COMMANDS.md` from the catalog and commit it
- [X] T014 [US1] Wire drift-check into CI (`.github/workflows/ci.yml`) so a stale `docs/COMMANDS.md` fails the build
- [X] T015 [P] [US1] Cross-platform discovery parity: extend `configs/claude/scripts/generate_cursor_rules.sh` to emit the discovery `.mdc`, and inject the **compact catalog index** into `configs/gemini/GEMINI.md` and `AGENTS.md` (Antigravity via existing symlink) — per the plan capability matrix

**Checkpoint**: US1 fully functional — discovery works in-session and as a drift-free doc across all platforms. **MVP deliverable.**

---

## Phase 4: User Story 2 - Contextual workflow hints (Priority: P2)

**Goal**: Event-driven, one-shot hints at recognized moments (pre-commit, PR-open, refactor-start, high-context), de-duplicated and prioritized, no hint on unrelated actions.

**Independent Test**: `git commit` surfaces a `/verify`/`/project-commit` hint; an unrelated action surfaces nothing.

### Tests for User Story 2 ⚠️ (write first, must FAIL)

- [X] T016 [P] [US2] `tests/python/command_help/test_guidance_hint.py` — moment→command mapping, ref resolution against catalog, dedup by `dedup_key`, priority ordering, one-shot emission
- [X] T017 [P] [US2] `tests/bats/guidance_hint_hook.bats` — hook fires once at a recognized moment; no hint on an unrelated Bash command

### Implementation for User Story 2

- [X] T018 [US2] Create `configs/claude/config/hint_registry.yml` — moments + hint rules per `contracts/hint-registry-schema.md` (pre-commit, pr-open, high-context, refactor-start)
- [X] T019 [US2] Implement `configs/claude/scripts/guidance_hint.py` — load registry, resolve `command_refs` against catalog, dedup/priority, emit one-shot text, fail-open (exit 0 when nothing to say) (depends on T005, T018)
- [X] T020 [US2] Wire Claude Code hooks via `ai-hooks-integration` (PreToolUse Bash matcher for `git commit` / `gh pr|glab mr`; context-high signal) to call `guidance_hint.py`
- [X] T021 [P] [US2] Cross-platform hint delivery: Gemini + Cursor via `ai-hooks-integration`; Codex + Antigravity standing-line fallback (documented gap per plan matrix)

**Checkpoint**: US1 + US2 both work independently; hints never enter always-loaded context.

---

## Phase 5: User Story 3 - Tunable reminders (Priority: P3)

**Goal**: Best-practice reminders, on by default, with global + per-category opt-out, verbosity, and rate-limiting; opt-out never dirties the tracked tree.

**Independent Test**: A reminder fires at most once per window; disabling reminders stops them while hints continue; `enabled: false` stops everything.

### Tests for User Story 3 ⚠️ (write first, must FAIL)

- [X] T022 [P] [US3] Extend `tests/python/command_help/test_guidance_hint.py` — preference gating (global, per-category, verbosity), defaults←local merge order, rate-limit window, single-opt-out → zero subsequent (SC-004)

### Implementation for User Story 3

- [X] T023 [US3] Create shipped defaults `configs/claude/config/guidance.yml` (all enabled) per `contracts/guidance-prefs-schema.md`
- [X] T024 [US3] Implement preference loading + merge in `configs/claude/scripts/guidance_hint.py` — `guidance.yml` ← `~/.claude/config/guidance_local.yml` (local wins); apply gating resolution order (depends on T019, T023)
- [X] T025 [US3] Implement rate-limit state under `~/.claude/state/guidance/` (last-fired timestamps; fail-open if absent) and the opt-out write path (writes only `guidance_local.yml`)
- [X] T026 [US3] Add reminder-category rules to `configs/claude/config/hint_registry.yml` (token-economy, verify-before-commit, stale-plan) with `rate_limit` windows
- [X] T027 [US3] Deploy & gitignore wiring: the shipped `guidance.yml` deploys via the existing `configs/claude/config/` copy (no new bootstrap logic). The user-local `~/.claude/config/guidance_local.yml` is **NOT** seeded by bootstrap — it is created lazily on first opt-out (T025), and an absent local file means "all defaults apply" (T024 merge must handle this). Add the `guidance_local.yml` path to the appropriate gitignore (idempotent, Constitution V)

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T028 [P] Update `docs/COMMANDS.md` header/index references, `README.md` command section, and `CHANGELOG.md`
- [X] T029 [P] Add a `context_budget` assertion (extend `tests/bats/context_budget.bats`) proving the injected guide index stays under threshold as the catalog grows (FR-009/SC-006)
- [X] T030 Run `quickstart.md` end-to-end to validate the SC-005 guidance chain (verify → commit → open PR)
- [X] T031 Full gate pass: `pytest tests/python/`, `npx bats tests/bats/`, `shellcheck configs/claude/scripts/*.sh`, `yamllint configs/claude/config/*.yml`
- [X] T032 Parallel-agent cross-verification before merge (Constitution II — change >200 lines): `parallel_agent.py --json --validate` over the new scripts/skill
- [X] T033 [P] SC-003 measurement harness in `tests/python/command_help/test_guidance_hint.py` — over the registered Workflow Moments + a fixed unrelated-action sample, assert relevant command surfaced for ≥90% of moments and ≤5% false-positive on unrelated actions (the SC-003 population metric, beyond the per-moment mechanism tests T016/T017)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: no dependencies — start immediately
- **Foundational (P2)**: depends on Setup; **BLOCKS all user stories** (catalog is the backbone)
- **US1 (P3)**: depends on Foundational
- **US2 (P4)**: depends on Foundational (uses catalog for ref resolution); independent of US1
- **US3 (P5)**: depends on US2 (extends `guidance_hint.py` + `hint_registry.yml`)
- **Polish (P6)**: depends on all desired stories

### Critical path

T001 → T004 → T005 → (US1: T010/T011/T012 → T013 → T014) → MVP. US2/US3 follow.

### Within each story

Tests written and FAILING first → catalog/config → script logic → skill/hook wiring → cross-platform reach.

### Parallel Opportunities

- Setup: T002, T003 in parallel
- Foundational: T004 (test) can be authored while T002/T003 land
- US1 tests T007/T008/T009 in parallel; then T015 parallels T010–T012 (different files)
- US2 tests T016/T017 in parallel; T021 parallels core once T019 lands
- Polish: T028, T029 in parallel

---

## Parallel Example: User Story 1

```bash
# Tests first (parallel — different files):
Task: "test_generate_commands_doc.py (render + --check)"
Task: "commands_doc_drift.bats (drift exit codes)"
Task: "command_help_cli.bats (search/group/unavailable)"

# Then cross-platform reach parallels core script work:
Task: "generate_commands_doc.py renderer"          # T011
Task: "extend generate_cursor_rules.sh + guide index injection"  # T015
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (catalog) → 3. Phase 3 US1 → **STOP & validate** discovery + drift-free doc across platforms → demo.

### Incremental Delivery

Foundation → US1 (MVP: discovery) → US2 (hints) → US3 (tunable reminders). Each completed story is an **incrementally deployable** stopping point that never breaks a prior one and is independently testable. Note the order is fixed where there is a real dependency: **US3 extends US2's `guidance_hint.py` + `hint_registry.yml`, so US3 cannot ship without US2** (US1 and US2 are independent of each other).

---

## Notes

- [P] = different files, no incomplete-task dependency.
- Tests must FAIL before implementation (Constitution + repo verification norm).
- Hints are one-shot output — never injected into always-loaded context (FR-009).
- Existing skills get `category:` frontmatter incrementally; until then the taxonomy `overrides` map or `uncategorized` covers them (no mass rename — clarify 2026-06-21).
- Commit after each task or logical group; honor the parallel-agent gate (T032) before opening the PR.
