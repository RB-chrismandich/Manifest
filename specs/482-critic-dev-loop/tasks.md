# Tasks: Critic-Driven Development Loop (CDDL)

**Input**: Design documents from `/specs/482-critic-dev-loop/`

**Prerequisites**: plan.md, spec.md, research.md (D1–D13), data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the feature's test strategy is spec-mandated (research D13, plan Testing
context, constitution Principle VI Verify gate). Write each test task FIRST and confirm it
fails before implementing its module.

**Organization**: Tasks are grouped by user story (spec.md US1–US4) so each story is an
independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (US1–US4) — user-story phases only
- Every task names exact file paths

## Path Conventions

Monorepo layout per plan.md Project Structure: orchestrator package at
`configs/claude/scripts/cddl/` with entry shim `configs/claude/scripts/cddl_loop.py`;
role prompts at `configs/claude/prompts/cddl/`; tests at `tests/python/cddl/` and
`tests/bats/`; skill source of truth at `.skillshare/skills/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and shared test fixtures every later task builds on.

- [X] T001 Create the `cddl` package skeleton per plan.md Project Structure: `configs/claude/scripts/cddl/__init__.py` plus empty stubs `cli.py`, `context.py`, `roles.py`, `invoke.py`, `verdicts.py`, `loop.py`, `candidate.py`, `gitops.py`, `verify.py`, `persistence.py`, and the test directory `tests/python/cddl/`
- [X] T002 Create shared pytest fixtures in `tests/python/cddl/conftest.py`: injectable fake runner for the `CDDL_CLI` seam (research D4), tmp git-repo factory (feature branch + clean tree), tmp `MANIFEST_STATE_ROOT`, and a minimal speckit fixture feature dir (spec.md + plan.md)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The five shared modules (role loading, verdict parsing, LLM invocation,
artifact discovery, run persistence) plus the three role prompts — required by every
user story's pre-flight and loop machinery.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Write role-definition validation tests in `tests/python/cddl/test_roles.py` per contracts/role-definition.md: missing/unreadable file, unparseable frontmatter, `name` ≠ file stem, empty `name`/`description`/`model`/body, reserved `provider` key rejected, unknown keys warn-and-ignore
- [X] T004 [P] Write verdict-parser tests in `tests/python/cddl/test_verdicts.py` per contracts/verdict-format.md fixtures: happy path per decision, spoof fixtures (approval token quoted in rejection prose; `cddl-verdict` example inside a `markdown` fence; quoted token with no real block), truncated JSON, duplicate blocks (last wins), wrong `role`, phase-inappropriate decision (`approve` in phase 1), empty findings on `reject`/`questions`, no block at all
- [X] T005 [P] Write invocation-seam tests in `tests/python/cddl/test_invoke.py` per research D4/D11: prompt delivered via stdin (argv fixed flags only), `TimeoutExpired` → failed call, exactly one retry then abort, per-call timeout capped by remaining run budget
- [X] T006 [P] Write discovery tests (speckit + explicit paths) in `tests/python/cddl/test_context.py`: speckit fixture resolution via the `spec_review.sh` seam, explicit `--spec`/`--plan` override wins (FR-001), missing plan recorded and disclosed rather than failing (spec edge case), tasks artifact ignored (FR-002)
- [X] T007 [P] Write persistence tests in `tests/python/cddl/test_persistence.py`: run-id format `YYYYMMDDTHHMMSSZ-<4char>`, run dir chmod 700 under `<state-root>/cddl/runs/<repo-slug>/<run-id>/`, `state.json` atomic rewrite, audit append via stubbed `audit_log.sh` is fail-open (audit failure never blocks)
- [X] T008 [P] Implement role loading + pre-flight validation in `configs/claude/scripts/cddl/roles.py` (RoleDefinition per data-model.md; exit-6 error paths name the offending file)
- [X] T009 [P] Implement the fail-closed verdict parser in `configs/claude/scripts/cddl/verdicts.py` (last `cddl-verdict` fenced block, strict `json.loads`, role/decision/findings validation per contract)
- [X] T010 [P] Implement the LLM invocation seam in `configs/claude/scripts/cddl/invoke.py` (`[$CDDL_CLI, "-p", "--model", <alias>]`, stdin payload, subprocess timeout, one bounded retry, run-budget cap, injectable runner parameter)
- [X] T011 [P] Implement artifact discovery in `configs/claude/scripts/cddl/context.py`: shell out to `bash -c 'source .../spec_review.sh; resolve_artifacts …'` parsing `role<TAB>path` lines (research D2; `resolve_artifacts` delegates to the file-root-aware `discover_artifacts`, so a FILE target is the explicit spec paired within its own layout tree), explicit-path seeding, FeatureContext snapshot with plan-absence disclosure
- [X] T012 [P] Implement run persistence in `configs/claude/scripts/cddl/persistence.py`: run-dir creation, `state.json` atomic writes, `context.md` snapshot, audit append shelling to `audit_log.sh` with `CDDL_AUDIT_FILE` exported as `AUDIT_LOG_FILE` — the writer's generic file target added for CDDL (contracts/cli-interface.md env table), fail-open
- [X] T013 [P] Author the three role prompts `configs/claude/prompts/cddl/implementer.md`, `qa-critic.md`, `arch-critic.md`: frontmatter `name` (= file stem) / `description` / `model: sonnet` alias, bodies carrying the role charter and review criteria only — the `cddl-verdict`/`cddl-file` output-grammar instruction is appended per invocation by the orchestrator (contracts/role-definition.md prompt assembly), keeping the grammar single-sourced

**Checkpoint**: Foundation ready — user story phases can begin.

---

## Phase 3: User Story 1 - Critic-gated implementation of a speckit feature (Priority: P1) 🎯 MVP

**Goal**: One command over a speckit feature dir runs implementer → verification → dual
critic audit, staging changes on the feature branch only on dual structured approval.

**Independent Test**: Run the loop against a small fixture feature (spec + plan) on a
scratch feature branch with a stubbed CLI. Verify staged (uncommitted) changes exist, the
run records explicit approval from both critics for the final iteration, and no commit,
push, or merge occurred.

### Tests for User Story 1 (write first, must fail)

- [X] T014 [P] [US1] Write candidate-format/confinement tests in `tests/python/cddl/test_candidate.py` per contracts/candidate-format.md fixture list: traversal `../escape`, absolute `/etc/x`, symlink-parent escape, `.git/hooks/x`, space-in-path, backslash pseudo-traversal, zero-block output (`no-candidate`), delete-block, byte-identical stall flag, multi-file happy path with atomic apply + `written_paths`
- [X] T015 [P] [US1] Write git-safety tests in `tests/python/cddl/test_gitops.py` per research D9: default-branch refusal, dirty-tree refusal, `--allow-dirty` override, staging exactly the approved candidate's paths (`git add -- <paths>`, pre-existing dirt never staged, phantom created-then-deleted paths skipped), never commit/push/merge
- [X] T016 [P] [US1] Write verification-gate tests in `tests/python/cddl/test_verify.py` per research D8: auto-detect matrix (`tests/bats/`→bats, `tests/python/`|`pyproject.toml`→pytest, `package.json` test script→npm, `Makefile` test target→make), multiple detections run in sequence, `--verify-cmd` override, no-gates skip recorded and disclosed
- [X] T017 [P] [US1] Write phase-2 loop tests in `tests/python/cddl/test_loop.py` (fake runner): dual approval → `success` + staged; one reject → that iteration's findings present in iteration N+1 implementer context (FR-007); ceiling exhaustion → `ceiling_failure`, candidate left unstaged; verification failure → deficiency fed back and critics NOT invoked (FR-009); stalled candidate counts toward ceiling, never success; run wall-clock expiry → `aborted`

### Implementation for User Story 1

- [X] T018 [P] [US1] Implement candidate parsing, confinement validation, and atomic apply in `configs/claude/scripts/cddl/candidate.py` (relative-only paths, no `..`, no backslashes, parent-realpath containment inside `realpath(repo_root)`, no `.git/`, all-or-nothing rejection with `confinement` deficiency; pre-images of files about to be overwritten/deleted are backed up to `iterations/<n>/backup/`)
- [X] T019 [P] [US1] Implement git pre-flight and staging in `configs/claude/scripts/cddl/gitops.py` (default-branch resolution with fallback detection, porcelain dirty check, explicit-path staging on success only — filtered to paths that exist or are tracked so phantom pathspecs never abort an approved run)
- [X] T020 [P] [US1] Implement the verification gate in `configs/claude/scripts/cddl/verify.py` (auto-detect + `--verify-cmd`, output captured to `iterations/<n>/verify.log`)
- [X] T021 [US1] Implement the phase-2 state machine in `configs/claude/scripts/cddl/loop.py`: implement→verify→critique iteration cycle, deficiency feedback assembly, ceilings/deadline enforcement, minimal phase-1 pass-through (both critics `complete` in round 1 → straight to phase 2), state transitions + invariants per data-model.md, written-files disclosure in every implementer prompt (leftovers are never auto-reverted per clarification Q1), and basic report.md via the finish path
- [X] T022 [US1] Implement `start` and `status` subcommands + per-repo lock in `configs/claude/scripts/cddl/cli.py` (arg parsing per contracts/cli-interface.md flags/env, backend probe in pre-flight — missing/unauthenticated `$CDDL_CLI` → exit 6 with an actionable auth message before any model call (FR-012), lock under `${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/locks/<repo-slug>.lock` (state-root confined per FR-017) with stale threshold mirroring `loop_lock.sh`, held lock → exit 6 naming the owning run; `status --run` locates runs by id under the state root so it works from any cwd)
- [X] T023 [US1] Implement the entry shim `configs/claude/scripts/cddl_loop.py`: `--help` ≤15 lines exit 0 before any config/state lookup, `err()`-style stderr routing, stable exit-code contract (0/2/3/4/5/6/7), delegates to `cddl.cli` (FR-016, script conventions)
- [X] T024 [US1] Write bats CLI tests in `tests/bats/cddl_loop.bats` (PATH-stubbed `claude` per the `git_ops.bats` mock-bin pattern): `--help` contract, usage error exit 2, pre-flight exit 6 (default branch, dirty tree, invalid role file, unresolvable target, no usable backend, held lock), stubbed happy path → exit 0 with staged fixture file

**Checkpoint**: MVP — the critic-gated loop works end-to-end on a speckit fixture.

---

## Phase 4: User Story 2 - Clarification gate before any code (Priority: P2)

**Goal**: Both critics interrogate the spec/plan before implementation; operator answers
feed a durable context; phase 2 starts only on dual structured `complete`.

**Independent Test**: Feed a fixture spec containing a deliberately ambiguous requirement.
Verify the loop surfaces critic questions, produces no implementation output before the
gate passes, and persists the operator's answers into the run context used by later phases.

### Tests for User Story 2 (write first, must fail)

- [X] T025 [US2] Extend `tests/python/cddl/test_loop.py` with clarification-gate tests: ambiguous fixture → `questions_pending` (exit-3 state) with `questions.md` written per-critic; zero implementation output of any kind before gate pass; one `complete` + one `questions` → still pending (dual signal required, FR-003); answers appended to context and present in every later iteration's persisted context; round limit exhausted with open questions → `gate_failure` listing unresolved questions and zero code produced (FR-004)

### Implementation for User Story 2

- [X] T026 [US2] Implement phase-1 clarification rounds in `configs/claude/scripts/cddl/loop.py` and question/answer persistence (`questions.md`, `answers-<round>.md`, context amendment) in `configs/claude/scripts/cddl/persistence.py`
- [X] T027 [US2] Implement the `answer` re-entry subcommand in `configs/claude/scripts/cddl/cli.py` (`--run <run-id> --answers-file <path>`, run located by id under the state root when the cwd is not the target repo, next round execution, gate-pass → phase 2 within the same invocation, exit 3/4 wiring per contracts/cli-interface.md)
- [X] T028 [US2] Extend `tests/bats/cddl_loop.bats` with the re-entrant flow: stubbed critics ask questions → exit 3 + `questions.md` present → `answer` re-entry with answers file → gate passes → run completes

**Checkpoint**: The interactive gate works; US1 behavior unchanged when critics have no questions.

---

## Phase 5: User Story 3 - Same loop over a superpowers doc pair (Priority: P3)

**Goal**: The same command resolves a superpowers design doc + paired plan and behaves
identically, never demanding a tasks artifact.

**Independent Test**: Run the loop against a fixture superpowers design doc with a paired
plan. Verify the run resolves both artifacts, completes the same phases, and never reports
a missing tasks artifact.

### Tests for User Story 3 (write first, must fail)

- [X] T029 [US3] Extend `tests/python/cddl/test_context.py` with superpowers-layout tests: paired design/plan resolution via discovery precedence, embedded tasks never reported missing (FR-002), resolved layout recorded in the run log (spec edge case), neither-layout target → pre-flight refusal naming both supported layouts with zero model calls and zero state mutation (US3 scenario 3)

### Implementation for User Story 3

- [X] T030 [US3] Complete superpowers handling in `configs/claude/scripts/cddl/context.py`: layout-type propagation from the discovery seam, unresolvable-target actionable refusal (exit 6), resolved-layout entry in the run record
- [X] T031 [US3] Extend `tests/bats/cddl_loop.bats` with a superpowers fixture discovery case and an unresolvable-target refusal case

**Checkpoint**: Both supported layouts run identically through the same entry point.

---

## Phase 6: User Story 4 - Diagnosable run history (Priority: P4)

**Goal**: Any failed run identifies the blocking critic, deficiency, and iteration from
persisted artifacts alone.

**Independent Test**: Force a run to fail at a low iteration ceiling. Verify the persisted
run artifacts identify the blocking critic and its outstanding findings for the final
iteration, without re-running.

### Tests for User Story 4 (write first, must fail)

- [X] T032 [US4] Extend `tests/python/cddl/test_persistence.py` and `tests/python/cddl/test_loop.py` with diagnosability tests: per-iteration artifact completeness (`candidate.md`, `files.json`, `verify.log`, raw critic outputs, `verdicts.json`, timestamps — US4 scenario 1); ceiling-failure `report.md` lists outstanding deficiencies per critic for the last iteration (US4 scenario 2); clarification answers appear in each iteration's persisted context (US4 scenario 3); an audit event per state transition (FR-010); interrupted-run state evident from `state.json`/report (spec edge case)

### Implementation for User Story 4

- [X] T033 [US4] Enrich `report.md` generation (lives with the state machine in `configs/claude/scripts/cddl/loop.py`): status, blocking critic + per-critic outstanding deficiencies, staged/unstaged disposition incl. rejected-iteration leftovers, backup-based restore instructions (`cp` from `iterations/<n>/backup/`, never `git checkout` — safe under `--allow-dirty`), stall flags
- [X] T034 [US4] Wire audit events at every state transition in `configs/claude/scripts/cddl/loop.py` (fail-open per FR-010) and make interrupted runs evident (persisted phase/status shows incomplete state)
- [X] T035 [US4] Enrich the `status` subcommand output in `configs/claude/scripts/cddl/cli.py`: latest-run summary with blocking critic and top outstanding deficiency (SC-004 five-minute diagnosis path)

**Checkpoint**: All four stories independently verifiable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Skill packaging, registration, derived artifacts, smoke coverage, repo gates.

- [X] T036 Create the skill `.skillshare/skills/spec-implement-loop/SKILL.md`: frontmatter (name + description ≤ ~290 chars, fitting the 22 000-byte aggregate budget at deployed size) and body wiring the conversational flow — run `start`, relay `questions.md` to the operator, re-invoke `answer` until the gate resolves, then report the phase-2 outcome (research D6/D12)
- [X] T037 [P] Add the `tool_policies` entry for `spec-implement-loop` in `configs/claude/config/command_config.yml`: allowed `[Bash, Read]`, `parallel_agents: never`, `validation_tier: 1`, `subagents: never` with rationale (research D12)
- [X] T038 Regenerate derived artifacts after skill add: `generate_cursor_rules.sh` (cursor `.mdc`), `generate_commands_doc.py --inject-guides` (docs/COMMANDS.md + GEMINI/AGENTS command-index blocks), and skill-count strings (research D12 regeneration chain)
- [X] T039 Append the Lite-tier smoke entry to `smoke-catalog/manifest.yaml` via `smoke_test.py append`: hermetic mktemp fixture repo + stub CLI approving on iteration 1; asserts exit 0, staged file present, `report.md` exists — constitution Principle VI Verify gate for the shipped user-facing workflow (MANDATORY, research D13)
- [X] T040 [P] Write deployment-safety tests in `tests/bats/deploy_cddl.bats` (SC-008, FR-014): a deploy places the three role prompts under the home `prompts/cddl/`, writes zero files into the `agents/` subagent registry (byte-identical before/after), a redeploy preserves an operator-added file alongside the role prompts, and removing the repo assets retires the deployed copies via the deploy-reconcile flow with nothing else touched
- [X] T041 Run the full repo gates and fix any regression: `bats tests/bats/`, `pytest tests/python/`, ruff, `yamllint configs/claude/config/*.yml`, skill-naming gate, context-budget gate at deployed size, derived-docs consistency (SC-007)
- [X] T042 Validate quickstart.md end-to-end on a scratch feature branch (start → questions → answer → staged outcome → run-dir inspection) and fix any doc drift, including the merge-mode `--ignore-existing` role-prompt-update note

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup — BLOCKS all user stories. Within it, test tasks (T003–T007) precede their paired implementations (T008–T012); T013 is independent.
- **US1 (Phase 3)**: depends on Foundational. T018–T020 need T014–T016; T021 needs T018–T020 (+T009/T010/T012); T022 needs T021 (+T011); T023 needs T022; T024 needs T023 and T013.
- **US2 (Phase 4)**: depends on US1's loop/cli (T021, T022) — extends the same state machine.
- **US3 (Phase 5)**: depends on Foundational T011 and US1's pre-flight path (T022); independent of US2.
- **US4 (Phase 6)**: depends on US1 (iteration artifacts) and reads US2's clarification records when present; T033/T034 before T035.
- **Polish (Phase 7)**: T036 after US2 (the skill mediates the gate); T038 after T036+T037; T039 after US1; T040 after T013 (deploy assets exist); T041/T042 last.

### User Story Dependencies

- **US1 (P1)**: only Foundational — the MVP.
- **US2 (P2)**: builds on US1's loop and CLI files (sequential after US1).
- **US3 (P3)**: only Foundational + US1's entry path; can run in parallel with US2 (different files: context.py vs loop.py/cli.py — coordinate on the shared bats file, T028 vs T031).
- **US4 (P4)**: after US1; scenario 3 coverage needs US2 done.

### Within Each User Story

Tests first (must fail) → modules ([P] across different files) → state-machine/CLI wiring → bats.

### Parallel Opportunities

- Foundational: T003–T007 together; then T008–T013 together (six different files).
- US1: T014–T017 together; then T018–T020 together.
- US2 and US3 phases can proceed in parallel (different modules); serialize only the two bats-file tasks (T028, T031).
- Polish: T037 and T040 parallel with T036.

---

## Parallel Example: User Story 1

```bash
# Test wave (all different files):
Task: "T014 candidate/confinement tests in tests/python/cddl/test_candidate.py"
Task: "T015 git-safety tests in tests/python/cddl/test_gitops.py"
Task: "T016 verification-gate tests in tests/python/cddl/test_verify.py"
Task: "T017 phase-2 loop tests in tests/python/cddl/test_loop.py"

# Module wave (all different files):
Task: "T018 candidate.py"  Task: "T019 gitops.py"  Task: "T020 verify.py"
# Then sequentially: T021 loop.py → T022 cli.py → T023 cddl_loop.py → T024 bats
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup → Phase 2 Foundational (blocks everything).
2. Phase 3 US1 → **STOP and VALIDATE**: fixture run stages changes with dual approval, exit-code contract holds, no commit/push/merge.
3. That alone is the viable critic-gated implementation path for speckit features.

### Incremental Delivery

1. US1 (MVP: adversarially reviewed implementation) → validate.
2. US2 (clarification gate — the interactive touchpoint) → validate.
3. US3 (superpowers parity) and US4 (diagnosability) in either order or parallel.
4. Polish: skill + registration + smoke + deployment-safety + gates — the feature ships only after T039/T040/T041 (constitution Verify gate + SC-008 + SC-007).

---

## Notes

- Verify every test task fails before its implementation task starts (TDD).
- T017/T025/T032 share `test_loop.py`; T024/T028/T031 share `cddl_loop.bats`; T022/T027/T035 share `cli.py`; T021/T026/T034 share `loop.py`; T012/T026/T033 share `persistence.py` — never parallelize within those sets.
- Commit after each task or logical group (per-phase `/speckit-git-commit` hooks are registered).
- `/spec-audit-tasks` runs automatically after implement (after_implement hook) to audit completion.
