---

description: "Task list for parallel_agent.py modularization into agents/ package"
---

# Tasks: Parallel Agent Orchestration Modularization

**Input**: Design documents from `specs/001-modularize-parallel-agent/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/cli-contract.md ✅

**Tests**: Per-module unit tests are REQUIRED (FR-008). Existing integration tests must be updated (FR-007).

**Organization**: Tasks are grouped by user story. US1 (module extraction) must complete before US2 (per-module tests), since test files import from the new modules.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Extraction order constraint: `config.py` → `{validation.py, synthesis.py, runners.py}` → `orchestrator.py` → `cli.py` → shim → `__init__.py`

---

## Phase 1: Setup

**Purpose**: Establish the baseline and package skeleton before any code is moved.

- [x] T001 Capture baseline test results: run `pytest tests/python/test_parallel_agent.py -v` and save output to `specs/001-modularize-parallel-agent/baseline-test-results.txt`
- [x] T002 Create package directory and empty `__init__.py`: `mkdir -p configs/claude/scripts/agents && touch configs/claude/scripts/agents/__init__.py`
- [x] T003 [P] Create per-module test directory: `mkdir -p tests/python/agents && touch tests/python/agents/__init__.py`

---

## Phase 2: Foundational — config.py (Blocking Prerequisite)

**Purpose**: Extract `Config`, `ServiceConfig`, `Logger`, and `RateLimiter` into `agents/config.py` first, since every other module imports from it. No user story work can begin until this phase is complete.

**⚠️ CRITICAL**: All subsequent module extractions depend on `agents/config.py` existing.

- [x] T004 Extract `Config` and `ServiceConfig` classes (lines 70–183 of `configs/claude/scripts/parallel_agent.py`) into `configs/claude/scripts/agents/config.py`; add stdlib-only imports (no cross-module deps)
- [x] T005 Append `Logger` class (lines 184–246) and `RateLimiter` class (lines 247–280) to `configs/claude/scripts/agents/config.py`
- [x] T006 Verify `agents/config.py` is independently importable: `cd configs/claude/scripts && python3 -c "from agents.config import Config, ServiceConfig, Logger, RateLimiter; print('config ok')"`

**Checkpoint**: `agents/config.py` importable independently — US1 extraction can now proceed in parallel.

---

## Phase 3: User Story 1 — Developer Isolates a Code Concern (Priority: P1) 🎯 MVP

**Goal**: Split the monolith into 6 focused modules so any single concern can be opened, read, and modified without touching unrelated code.

**Independent Test**: Run the full existing test suite against the new module structure; all tests pass and CLI behavior is identical (SC-003).

### Implementation for User Story 1

- [x] T007 [P] [US1] Extract `ValidationEngine` (lines 281–680) into `configs/claude/scripts/agents/validation.py`; import `Config` and `Logger` from `agents.config`
- [x] T008 [P] [US1] Extract `SynthesisEngine` (lines 681–810) into `configs/claude/scripts/agents/synthesis.py`; import `Config` and `Logger` from `agents.config`
- [x] T009 [P] [US1] Extract `BaseAgent`, `ClaudeAgent`, `GeminiAgent`, `CursorAgent`, `CodexAgent` (lines 811–1345) into `configs/claude/scripts/agents/runners.py`; import from `agents.config`
- [x] T010 [US1] Extract `Orchestrator` (lines 1346–1761) and `check_credits` (lines 1762–1870) into `configs/claude/scripts/agents/orchestrator.py`; import from `agents.config`, `agents.validation`, `agents.synthesis`, `agents.runners` (depends on T007, T008, T009)
- [x] T011 [US1] Extract `main()` and all argparse setup (lines 1871–2145) into `configs/claude/scripts/agents/cli.py`; import all agent classes and `Orchestrator` from respective modules (depends on T010)
- [x] T012 [US1] Write `configs/claude/scripts/agents/__init__.py` with full re-export of all public symbols: `Config`, `ServiceConfig`, `Logger`, `RateLimiter`, `ValidationEngine`, `SynthesisEngine`, `BaseAgent`, `ClaudeAgent`, `GeminiAgent`, `CursorAgent`, `CodexAgent`, `Orchestrator`, `check_credits`, `main` (depends on T011)
- [x] T013 [US1] Replace `configs/claude/scripts/parallel_agent.py` with thin shim (≤15 lines): `sys.path.insert`, `from agents.cli import main`, `asyncio.run(main())` (depends on T012)
- [x] T014 [US1] Verify all modules import without error: run `cd configs/claude/scripts && python3 -c "from agents import Config, ValidationEngine, SynthesisEngine, BaseAgent, Orchestrator, main; print('all imports ok')"`
- [x] T015 [US1] Run `pytest tests/python/test_parallel_agent.py -v` and confirm all tests that passed in T001 still pass (depends on T014)
- [x] T016 [US1] Verify SC-004: run `wc -l configs/claude/scripts/agents/*.py` and confirm each file is under 500 lines (runners.py ~550 and orchestrator.py ~540 are pre-approved exceptions per plan.md Complexity Tracking)

**Checkpoint**: All existing tests pass, CLI entry point works, all 6 modules exist — US1 is independently functional and demonstrable.

---

## Phase 4: User Story 2 — Developer Writes a Targeted Test (Priority: P2)

**Goal**: Each module ships with a dedicated unit test file so any concern can be tested in isolation without standing up the full orchestration pipeline.

**Independent Test**: Each per-module test file runs independently to exit 0: `pytest tests/python/agents/test_config.py -v` (and equivalent for each module).

### Tests for User Story 2 (FR-008 — REQUIRED)

- [x] T017 [P] [US2] Write `tests/python/agents/test_config.py`: migrate and adapt Config, ServiceConfig, Logger, and RateLimiter tests from `tests/python/test_parallel_agent.py`; import from `agents.config`
- [x] T018 [P] [US2] Write `tests/python/agents/test_validation.py`: migrate and adapt ValidationEngine tests; import from `agents.validation`
- [x] T019 [P] [US2] Write `tests/python/agents/test_synthesis.py`: migrate and adapt SynthesisEngine tests; import from `agents.synthesis`
- [x] T020 [P] [US2] Write `tests/python/agents/test_runners.py`: migrate and adapt BaseAgent and CodexAgent tests; import from `agents.runners`
- [x] T021 [P] [US2] Write `tests/python/agents/test_orchestrator.py`: migrate and adapt Orchestrator tests; import from `agents.orchestrator`
- [x] T022 [P] [US2] Write `tests/python/agents/test_cli.py`: migrate and adapt argument parsing tests; import from `agents.cli`

### Implementation for User Story 2

- [x] T023 [US2] Update `tests/python/test_parallel_agent.py` imports: replace `from parallel_agent import (Config, ...)` with per-module imports `from agents.config import Config, ServiceConfig, Logger, RateLimiter` etc. (FR-007)
- [x] T023a [P] [US2] Verify SC-002 isolation: run each per-module test file alone (e.g., `pytest tests/python/agents/test_config.py -v`, and equivalent for all 6 files) and confirm each exits 0 without requiring external agent connections or other module imports (depends on T017–T022)
- [x] T024 [US2] Run full test suite including all per-module and updated integration tests: `pytest tests/python/ -v` — all tests must pass, zero failures (depends on T017–T023a)

**Checkpoint**: Each module has an independent test file; `pytest tests/python/agents/test_config.py` (and all others) runs to exit 0 without touching other modules.

---

## Phase 5: User Story 3 — Contributor Understands the Codebase (Priority: P3)

**Goal**: Validate that the module structure is navigable — a contributor can locate any concern within 2 minutes without text search (SC-001).

**Independent Test**: Walk through `quickstart.md` step-by-step and confirm each command produces the expected output.

### Implementation for User Story 3

- [x] T025 [P] [US3] Walk through `specs/001-modularize-parallel-agent/quickstart.md` steps 1–6 verbatim; update any step where the command or expected output has drifted from the actual implementation
- [x] T026 [US3] Verify SC-001: starting from the `agents/` directory listing only (no grep), locate "where does consensus scoring happen?" in under 2 minutes; add a one-line docstring to the `Orchestrator` class in `configs/claude/scripts/agents/orchestrator.py` confirming this is the consensus coordination module

**Checkpoint**: quickstart.md is accurate; consensus scoring location is findable within 2 minutes by file structure alone.

---

## Phase 6: Polish & Pre-Merge Gate

**Purpose**: Final equivalence verification, cleanup, and mandatory parallel agent review (Constitution Principle II — MUST).

- [x] T027 [P] Verify behavioral equivalence: compare CLI `--help` output before and after (`python configs/claude/scripts/parallel_agent.py --help`) — all flags must be present (SC-003)
- [x] T028 Run final full test suite including all per-module and integration tests: `pytest tests/python/ -v` — zero failures required; this is the final regression gate covering all modules added in US1 and US2
- [x] T029 [P] Remove dead code: confirm the original monolith body in `parallel_agent.py` is fully replaced by the shim (no old class definitions remain in the entry-point file)
- [ ] T030 **[REQUIRED MERGE GATE]** Constitution Principle II: run parallel agent cross-verification before merging — `~/.claude/scripts/parallel_agent.py --validate --review configs/claude/scripts/agents/`; this is a MUST per the constitution for >200-line modifications; PR MUST NOT merge without a passing review at ≥50% consensus

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (Phase 2) completion
  - T007, T008, T009 can run in parallel (no inter-dependency)
  - T010 depends on T007, T008, T009
  - T011 depends on T010; T012 depends on T011; T013 depends on T012
- **US2 (Phase 4)**: Depends on US1 (Phase 3) completion (modules must exist before test files import from them)
  - T017–T022 can all run in parallel (different files)
  - T023a depends on T017–T022; T023 depends on T017–T022; T024 depends on T017–T023a
- **US3 (Phase 5)**: Depends on US2 completion (quickstart.md references updated test commands)
- **Polish/Gate (Phase 6)**: Depends on US3 completion; T030 is a hard merge gate — PR must not merge without it

### Within Each User Story

- config.py extracted before all others (Foundational)
- validation.py, synthesis.py, runners.py extracted in parallel
- orchestrator.py after the above three
- cli.py after orchestrator.py
- shim after cli.py
- `__init__.py` after shim
- per-module test files in parallel (once modules exist)
- integration test import update after all per-module tests written

---

## Parallel Opportunities

### Phase 3: US1 parallel window (T007, T008, T009)

```bash
# These three can be worked simultaneously (different files, same config dependency):
Task: "Extract ValidationEngine into configs/claude/scripts/agents/validation.py"
Task: "Extract SynthesisEngine into configs/claude/scripts/agents/synthesis.py"
Task: "Extract all agent classes into configs/claude/scripts/agents/runners.py"
```

### Phase 4: US2 parallel window (T017–T022)

```bash
# All six per-module test files can be written simultaneously:
Task: "Write tests/python/agents/test_config.py"
Task: "Write tests/python/agents/test_validation.py"
Task: "Write tests/python/agents/test_synthesis.py"
Task: "Write tests/python/agents/test_runners.py"
Task: "Write tests/python/agents/test_orchestrator.py"
Task: "Write tests/python/agents/test_cli.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational — config.py extraction (T004–T006)
3. Complete Phase 3: US1 extraction + regression verification (T007–T016)
4. **STOP and VALIDATE**: Run `pytest tests/python/test_parallel_agent.py -v` and verify `python parallel_agent.py --help` shows all flags
5. The tool is fully functional and modularly organized at this point

### Incremental Delivery

1. MVP above → test suite passes → shim works
2. Add US2 (T017–T024) → per-module tests pass independently → SC-005 satisfied
3. Add US3 (T025–T026) → quickstart validated → SC-001 verified
4. Polish/Gate (T027–T030) → equivalence confirmed → mandatory parallel agent review (T030) before merge

### Parallel Team Strategy

With two developers after Phase 2 completes:
- Developer A: T007 (validation.py) + T017 (test_validation.py after US1 done)
- Developer B: T008 (synthesis.py) + T009 (runners.py) + T019, T020 (tests after US1 done)
- Then together: T010 (orchestrator), T011 (cli), T012 (__init__), T013 (shim), T015 (regression)

---

## Notes

- [P] tasks = different files, no dependencies — safe to parallelize
- [Story] label maps task to specific user story for traceability
- T007, T008, T009 are the core parallel window — the biggest time savings
- Each module must not import from modules that depend on it (no circular imports)
- The dependency graph is strictly: stdlib ← config ← {validation, synthesis, runners} ← orchestrator ← cli
- Commit after each phase checkpoint (T006, T016, T024, T026, T030)
- `runners.py` (~550 lines) and `orchestrator.py` (~540 lines) exceed SC-004 by design; see plan.md Complexity Tracking
- **Commit atomicity** (spec.md Edge Case): NEVER commit a partial extraction (e.g., one module moved but others not yet). Commit only at phase checkpoints — T006, T016, T024, T026 — when the codebase is in a fully working state
- **T030 is a hard merge gate**: do not raise a PR without first completing T030 (Constitution Principle II MUST)
