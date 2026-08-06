---
description: "Task list for Sub-Agent Dispatch Guidance for Skills"
---

# Tasks: Sub-Agent Dispatch Guidance for Skills

**Input**: Design documents from `specs/367-sub-agent-dispatch-guidance/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: The enforcement test is a first-class feature deliverable (FR-011), not optional TDD —
it lives in Phase 6 (US3) because it verifies the full-coverage outcome.

**Organization**: Grouped by user story. MVP = US1 (concrete triggers on the heaviest skills).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 (Setup/Foundational/Polish carry no story label)
- Exact file paths included. Repo root = `/Users/chrismandich/Documents/GitHub/Manifest/.claude/worktrees/sub-agent-use`

## Path Conventions

This is a configuration-as-code repo (no app runtime). Work touches:
`configs/claude/config/command_config.yml`, `configs/claude/CLAUDE.md`,
`.retired skill supply/skills/<skill>/SKILL.md`, and `tests/bats/`.

⚠️ **Same-file serialization**: Many tasks edit the single file
`configs/claude/config/command_config.yml`. Tasks editing it are **NOT** `[P]` with each other.
Tasks editing distinct `SKILL.md` files **are** `[P]`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm a green baseline before any edits.

- [X] T001 Confirm baseline is green: run `bats tests/bats/` and `yamllint configs/claude/config/command_config.yml`; record current pass state.
- [X] T002 Confirm authoritative skill count dynamically: `find .retired skill supply/skills -mindepth 1 -maxdepth 1 -type d -exec test -f '{}/SKILL.md' \; -print | wc -l` (expect 88) and that 58 lack a `tool_policies` entry — capture the missing list for Phase 6.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared selection rules and the config schema convention. **Everything else links to
these**, so they MUST land first.

**⚠️ CRITICAL**: No US1/US2/US3 task may begin until T003–T004 are complete.

- [X] T003 Author the shared **Sub-Agent Selection Rules** in a NEW read-on-demand reference `configs/claude/references/sub-agent-dispatch.md` (NOT inline in the auto-loaded CLAUDE.md — context_budget.bats allows only ~537 bytes headroom there). Content per research R2/R8 + data-model "Shared Selection Rules": native Task/Agent sub-agents vs `parallel_agent.py`; cross-platform fallback (Claude-only Task tool → inline or `parallel_agent.py` on Cursor/Gemini/Codex/Antigravity); no-recursion rule; ≥3-independent-unit default floor. Then add ONE pointer line to the "Reference Index" in `configs/claude/CLAUDE.md`.
- [X] T004 Add the `subagents` schema convention as a header comment block at the top of the `tool_policies:` block in `configs/claude/config/command_config.yml`, per `contracts/tool_policies.subagents.schema.md` (documents `subagents`, `subagent_trigger`, `subagent_rationale`; states config is authoritative over body prose).

**Checkpoint**: Shared rules + schema exist — skills can now reference them and record dispositions.

---

## Phase 3: User Story 1 - In-skill dispatch triggers (Priority: P1) 🎯 MVP

**Goal**: The heaviest, obviously-decomposable skills carry a concrete, checkable in-body dispatch
trigger that links the shared rules — proving the convention end-to-end on a representative set.

**Independent Test**: Read each targeted `SKILL.md`; confirm a directive trigger (condition + count +
per-agent task + link to shared rules) is present, and its threshold matches `subagent_trigger` in
`command_config.yml`.

- [X] T005 [US1] Set `subagents` (+ `subagent_trigger` where conditional) for the MVP set in `configs/claude/config/command_config.yml` (single-file, serial edit): `docs-all`=always; `deep-research`=always; `refactor-python`/`refactor-node`/`refactor-go`/`refactor-shell`/`refactor-terraform`=conditional `subagent_trigger: "independent_units >= 3"`; `repo-hygiene`=conditional; `pr-review`=conditional; `issue-triage`=conditional.
- [X] T006 [P] [US1] Reconcile existing dispatch prose in `.retired skill supply/skills/docs-all/SKILL.md` into the standard trigger form (per `contracts/skill-trigger.format.md`), linking `#sub-agent-selection-rules`; do not duplicate the rules.
- [X] T007 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/deep-research/SKILL.md` (one sub-agent per independent search/source cluster).
- [X] T008 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/refactor-python/SKILL.md` (one sub-agent per independent module/dimension when ≥3).
- [X] T009 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/refactor-node/SKILL.md`.
- [X] T010 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/refactor-go/SKILL.md`.
- [X] T011 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/refactor-shell/SKILL.md`.
- [X] T012 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/refactor-terraform/SKILL.md`.
- [X] T013 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/repo-hygiene/SKILL.md` (one sub-agent per PR/branch batch).
- [X] T014 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/pr-review/SKILL.md` (one sub-agent per open PR when ≥3).
- [X] T015 [P] [US1] Add dispatch trigger to `.retired skill supply/skills/issue-triage/SKILL.md` (one sub-agent per issue batch).
- [X] T016 [US1] Verify each MVP trigger's threshold equals its `subagent_trigger` in config (manual cross-check; precursor to the automated test).

**Checkpoint**: MVP — a representative set demonstrates the full convention and is independently reviewable.

---

## Phase 4: User Story 2 - Selection rules wired per skill (Priority: P2)

**Goal**: Every dispatching skill points to the right mechanism (native Task vs `parallel_agent.py`)
and always offers a path that works on the running assistant.

**Independent Test**: For a dual-mechanism skill, confirm its trigger states the selection rule and
names the cross-platform fallback; confirm a security/architectural skill routes cross-model
verification to `parallel_agent.py`.

- [X] T017 [US2] In `configs/claude/references/sub-agent-dispatch.md` selection-rules section, add the explicit mechanism-by-task-type table (parallel reads/research → native Task; independent cross-model verification of security/architecture/>200-line changes → `parallel_agent.py`; <3 units → inline) and the non-Claude fallback row.
- [X] T018 [US2] Ensure the `refactor-*` skills keep `parallel_agents: always` (external cross-verification, constitution Tier-1) AND carry their native `subagents` trigger — verify the two fields coexist without contradiction in `command_config.yml`.
- [X] T019 [P] [US2] In each MVP `SKILL.md` trigger (T006–T015), confirm the mechanism pointer + cross-platform fallback reference is present (amend any that only say "dispatch a sub-agent" without the selection link).
- [X] T020 [US2] Add a note to the selection-rules reference (`configs/claude/references/sub-agent-dispatch.md`) that dispatched sub-agents never re-dispatch (no recursion), referenced by all triggers (FR-008/FR-007).

**Checkpoint**: Mechanism selection is unambiguous and cross-platform-safe for every dispatching skill.

---

## Phase 5: User Story 3 - Full-coverage audit + enforcement (Priority: P3)

**Goal**: Every one of the 88 skill directories has a disposition; "never" skills carry a rationale;
an automated test enforces coverage + consistency; the contributor convention is documented once.

**Independent Test**: Run the enforcement test — it passes and reports a disposition for every skill
directory; spot-check rationales and triggers.

### Audit (dogfood sub-agent fan-out — this is the "when to dispatch" instruction in action)

- [X] T021 [US3] **Dispatch sub-agents to classify the remaining skills**: split the ~78 non-MVP skill directories into batches of ~10 and dispatch **one sub-agent per batch** (≥3 independent batches → fan out per the very rule this feature defines). Each sub-agent reads its batch's `SKILL.md` files and returns, per skill: proposed `subagents` disposition, `subagent_trigger` (if conditional), and a one-line rationale (if `never`). Consolidate into a single proposed-dispositions table. (Native Task sub-agents on Claude; inline/`parallel_agent.py` fallback otherwise.) Explicitly include the skills that **already** mention sub-agents — `plan-manage`, `ai-hooks-integration`, `speckit-implement-review` — so their existing dispatch prose is reconciled into the standard trigger form, not duplicated or contradicted (FR-012).
- [X] T022 [US3] Review the consolidated proposals for consistency (same disposition vocabulary, threshold defaults), resolving any disagreements before writing config.

### Write dispositions to the canonical store (single file → serial)

- [X] T023 [US3] Backfill `tool_policies` entries for the 58 skills with no entry in `configs/claude/config/command_config.yml`, each with `subagents` (+ `subagent_trigger`/`subagent_rationale`) and required existing fields (`allowed`/`forbidden`/`validation_tier`, `parallel_agents` where applicable).
- [X] T024 [US3] Add the `subagents` field to the 30 pre-existing `tool_policies` entries that lack it (not covered by T005), preserving their current `parallel_agents`/`trigger_condition`.

### Rationales + triggers for the long tail (distinct files → parallelizable in batches)

- [X] T025 [P] [US3] For every skill dispositioned `never`, ensure a one-line `subagent_rationale` (config) or `> Sub-agents: not used — <reason>.` marker in its `SKILL.md` body.
- [X] T026 [P] [US3] For every non-MVP skill dispositioned `always`/`conditional`, add the in-body dispatch trigger (per `contracts/skill-trigger.format.md`) linking the shared rules.

### Enforcement test + convention

- [X] T027 [US3] Implement `tests/bats/subagent_policy.bats` per `contracts/enforcement-test.contract.md`: assertions T1–T7 (dynamic skill enumeration; every skill has `subagents`; conditional⇒trigger; never⇒rationale; always/conditional⇒body trigger linking shared rules; no never-skill body instructs dispatch; advisory threshold form).
- [X] T028 [US3] Confirm the new test is auto-discovered by the existing CI bats job (`tests/bats/*.bats`); run `bats tests/bats/subagent_policy.bats` and make it pass.
- [X] T029 [US3] Author the contributor convention as a subsection beneath the selection rules in `configs/claude/references/sub-agent-dispatch.md` (FR-013/SC-007), porting `quickstart.md` content (the one documented place).

**Checkpoint**: 100% coverage, enforced in CI; convention is durable and discoverable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 Run `quickstart.md` end-to-end as a contributor would (add a throwaway dummy skill dir with no disposition → confirm T027 fails → remove it) to validate the forcing function. **Then demonstrate SC-006** on one `conditional` skill (e.g., `refactor-python`): trace that an input with ≥3 independent units triggers fan-out while a <3-unit input stays inline — confirming the trigger demonstrably gates behavior, not just that the threshold is recorded.
- [X] T031 [P] Run full gate: `bats tests/bats/`, `pytest tests/python/`, `yamllint configs/claude/config/command_config.yml`, `markdownlint` on edited docs; fix any drift (e.g., `commands_doc_drift.bats`).
- [X] T032 [P] Reconcile spec count note if any skill is added/removed during implementation (test is dynamic; just confirm no hardcoded number leaked into the test).
- [X] T033 Self-review for constitution Tier-1 (Principle II): ran `parallel_agent.py --review` cross-verification on the diff (architecture-wide change >200 lines). 3 agents launched; claude + antigravity completed (gemini failed on `IneligibleTierError` — CLI deprecated for individuals, infra not code). Substantive checks all passed (security/error-handling/breaking-changes ✅, Tier-2 1.0); the `BLOCKED` verdict was a false block from the consensus metric collapsing on the gemini failure, not a finding. **One real bug caught & fixed**: `tests/bats/subagent_policy.bats` opened `SKILL.md`/config without `encoding="utf-8"` → `UnicodeDecodeError` on a C/POSIX-locale CI runner without `C.UTF-8` (reproduced with coercion disabled: `'ascii' codec can't decode byte 0xe2`). Fixed both `open()` calls; test passes under forced `C` locale. Antigravity's "broken doc links" finding was a non-issue (inline code spans using the repo-root path convention, not markdown link targets).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no deps — start immediately.
- **Foundational (Phase 2)**: after Setup — **BLOCKS US1/US2/US3** (everything links the shared rules + schema).
- **US1 (Phase 3)**: after Foundational. Delivers MVP.
- **US2 (Phase 4)**: after Foundational; builds on US1's triggers (amends them) — run after US1 for the MVP set, but selection-rules table (T017/T020) can land alongside Foundational.
- **US3 (Phase 5)**: after Foundational; T026 reuses the trigger format proven in US1; the enforcement test (T027) needs all dispositions (T023–T026) written first.
- **Polish (Phase 6)**: after all desired stories.

### User Story Dependencies

- **US1 (P1)**: independent once Foundational done — the MVP.
- **US2 (P2)**: logically refines US1 triggers + the shared table; independently testable.
- **US3 (P3)**: full coverage + enforcement; the test depends on US1/US2/US3 dispositions existing.

### Within Each Story

- Config disposition (single file, serial) → SKILL.md triggers (distinct files, parallel) → verify.

### Parallel Opportunities

- T006–T015 (US1 SKILL.md triggers) — all `[P]` (distinct files).
- T021 batches — sub-agents run concurrently (the canonical fan-out).
- T025/T026 — `[P]` across distinct SKILL.md files.
- T031/T032 — `[P]`.
- ⚠️ All `command_config.yml` edits (T004, T005, T018, T023, T024) are **serial** — same file.

---

## Parallel Example: User Story 1 SKILL.md triggers

```text
# After T005 sets dispositions in config, dispatch trigger-writing in parallel (distinct files):
Task: "Add dispatch trigger to .retired skill supply/skills/refactor-python/SKILL.md"
Task: "Add dispatch trigger to .retired skill supply/skills/refactor-node/SKILL.md"
Task: "Add dispatch trigger to .retired skill supply/skills/refactor-go/SKILL.md"
Task: "Add dispatch trigger to .retired skill supply/skills/deep-research/SKILL.md"
```

## Parallel Example: User Story 3 audit fan-out (the feature, applied to itself)

```text
# T021 — one sub-agent per ~10-skill batch (≥3 batches → fan out):
Task: "Classify subagent disposition for skills batch 1 (a11y-audit … ci-setup) — return table"
Task: "Classify subagent disposition for skills batch 2 (ci-workflow… … health-check) — return table"
Task: "Classify subagent disposition for skills batch 3 (help … pin-known-bug…) — return table"
# Consolidate (T022) → write to config (T023/T024, serial).
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 Setup → 2. Phase 2 Foundational (shared rules + schema) → 3. Phase 3 US1 →
4. **STOP & VALIDATE**: heavy skills show concrete triggers, thresholds match config → demo.

### Incremental Delivery

US1 (MVP) → US2 (mechanism selection wired) → US3 (full audit + CI enforcement + convention).
Each step is independently testable and adds value without breaking the prior.

### Notes

- `[P]` = distinct files, no deps. Config-YAML edits are never `[P]` together.
- Commit after each phase; the enforcement test (T027) is the durable backstop.
- T033 satisfies constitution Principle II (cross-verify architecture-wide change before PR).
