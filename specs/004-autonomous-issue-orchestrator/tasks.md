---
description: "Task list for Autonomous Issue Implementation Orchestrator"
---

# Tasks: Autonomous Issue Implementation Orchestrator

**Input**: Design documents from `/specs/004-autonomous-issue-orchestrator/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — the spec requires deterministic, fixture-tested behavior (SC-002, SC-016) and the constitution's Development Workflow mandates `pytest tests/python/` + `bats tests/bats/` pass. Write tests first within each story; ensure they FAIL before implementation.

**Organization**: Tasks are grouped by the 5 user stories from spec.md to enable independent implementation and testing.

> **Terminology note**: "Phase 1–8" below are *implementation* phases (Setup, Foundational, US1–US5, Polish). They are distinct from the orchestrator's *runtime* "Phase 1–6" (the six pipeline stages in spec.md). When a task says "Phase 4 analysis-gate prompt", it refers to the runtime phase; the surrounding "## Phase N" headings refer to implementation phases.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5, mapping to spec.md user stories
- File paths follow plan.md structure: daemon under `configs/claude/scripts/orchestrator/`, config under `configs/claude/config/`, skill under `.skillshare/skills/issue-orchestrator/`, tests under `tests/python/` + `tests/bats/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding, config, and reusable assets

- [X] T001 Create orchestrator package skeleton (empty modules + `__init__.py`) in `configs/claude/scripts/orchestrator/` (daemon.py, pipeline.py, engine.py, consensus.py, audit.py, redact.py)
- [X] T002 [P] Create `configs/claude/config/orchestrator.yml` — phase order (1–6), `attempt_cap: 2`, `resume_poll: hourly`, consensus-threshold reference to `command_config.yml`, redaction pattern set, audit/state path
- [X] T003 [P] Add the `no-automation` block label (with color + description) to `configs/claude/config/labels.yml`
- [X] T004 [P] Copy the 7 runtime JSON Schemas from `specs/004-autonomous-issue-orchestrator/contracts/` into `configs/claude/scripts/orchestrator/schemas/`
- [X] T005 [P] Create the decision-engine skill scaffold `.skillshare/skills/issue-orchestrator/SKILL.md` with `name`/`description` frontmatter and phase-keyed prompt sections (1–6)
- [X] T006 [P] Create pytest fixtures dir `tests/python/fixtures/orchestrator/` (sample backlog, analysis results, verification results, PR feedback, secret-corpus) and a bats helper `tests/bats/orchestrator_helper.bash`

**Checkpoint**: Package, config, label, schemas, skill stub, and fixtures exist.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The engine↔daemon boundary and pipeline runner that EVERY user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Implement response-envelope loader + validator (against `schemas/response-envelope.schema.json`) with canonical field ordering in `configs/claude/scripts/orchestrator/engine.py`
- [X] T008 Implement the context-payload builder (phase directive + inputs + attempt + flags, per data-model.md) in `configs/claude/scripts/orchestrator/engine.py`
- [X] T009 Implement the engine invocation adapter — headless CLI-agent call via `parallel_agent.py` backend selection (R1) — in `configs/claude/scripts/orchestrator/engine.py` (depends on T007, T008)
- [X] T010 [P] Implement the per-run pipeline state machine + compact JSON state file (run_id, selected_issue, current_phase, attempt_counts, paused) in `configs/claude/scripts/orchestrator/pipeline.py` (R9)
- [X] T011 [P] Implement the issue/label/PR read+write wrapper over `git_ops.sh`/`git_platform.sh` in `configs/claude/scripts/orchestrator/daemon.py`
- [X] T012 Implement the daemon poll/dispatch loop + CLI (`--repo`, `--phase`, `--payload`, `--dry-run`, `--help` ≤15 lines) in `configs/claude/scripts/orchestrator/daemon.py` (depends on T009, T010, T011)
- [X] T013 [P] Foundational test: envelope validation (well-formed, extra-field rejection, status/payload invariants, and that all justification lives only in `reasoning_log` with none in structured fields, FR-004) in `tests/python/test_orchestrator_envelope.py`
- [X] T014 [P] Foundational test: pipeline state transitions + resumability in `tests/python/test_orchestrator_pipeline.py`
- [X] T015 [P] Foundational test: daemon `--help` and CLI arg handling in `tests/bats/orchestrator_cli.bats`

**Checkpoint**: A phase can be dispatched, validated, and persisted end-to-end (with stub prompts).

---

## Phase 3: User Story 1 — Prioritized Issue Selection (Priority: P1) 🎯 MVP

**Goal**: Given a backlog, rank issues and select the top one with justification + dependency notes; exclude `no-automation` issues.

**Independent Test**: Feed raw issues (some with dependencies, some labeled `no-automation`); confirm a complete ranking, a justified top choice, dependency notes, and that an unblocking issue out-ranks an isolated higher-severity one.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [X] T016 [P] [US1] Contract test: Phase 1 payload conforms to `phase1-prioritization.schema.json` in `tests/python/test_orchestrator_phase1_contract.py`
- [X] T017 [P] [US1] Integration test: unblock-vs-severity ranking, empty/all-held backlog, determinism, severity_source recorded in `tests/python/test_orchestrator_phase1.py`

### Implementation for User Story 1

- [X] T018 [US1] Author the Phase 1 prioritization prompt (rank by severity + dependencies + logical order; state unblock-vs-severity trade-off) in `.skillshare/skills/issue-orchestrator/SKILL.md`
- [X] T019 [US1] Implement metadata-first severity derivation with body-inference fallback + `severity_source` logging (FR-036) in `configs/claude/scripts/orchestrator/engine.py`
- [X] T020 [US1] Implement `no-automation` exclusion at selection (FR-037 selection path) + dependency-cycle detection in `configs/claude/scripts/orchestrator/pipeline.py`
- [X] T021 [US1] Wire Phase 1 payload validation against the schema into the dispatch path in `configs/claude/scripts/orchestrator/daemon.py`

**Checkpoint**: US1 is a standalone triage-recommendation engine, fully testable. **MVP boundary.**

---

## Phase 4: User Story 2 — Doubly-Gated Implementation Pipeline (Priority: P1)

**Goal**: Produce dependency-ordered verifiable tasks; block implementation on any pre-impl finding; block PR-open on any Tier 1 post-impl finding; cross-verify both gates by consensus.

**Independent Test**: Feed an approved spec → ordered tasks with acceptance criteria; dirty analysis → implementation blocked; an unmet acceptance criterion post-impl → PR-open blocked (Tier 1) even with tests green; Tier-2-only → PR opens with advisory annotations.

### Tests for User Story 2 ⚠️ (write first, ensure they FAIL)

- [X] T022 [P] [US2] Contract tests: Phase 3/4/5 payloads conform to their schemas in `tests/python/test_orchestrator_phase345_contract.py`
- [X] T023 [P] [US2] Integration test: doubly-gated flow — dirty-analysis block (SC-004), acceptance-unmet Tier 1 block, Tier-2-only pass, no PR opened with an unresolved Tier 1 finding (SC-011), and `no-automation` applied **mid-pipeline** halts before the next advance (SC-015/FR-037) — in `tests/python/test_orchestrator_gates.py`
- [X] T024 [P] [US2] Test: consensus threshold mapping (≥80/50–79/<50 → proceed/flag/escalate; <50% always escalates, SC-013) in `tests/python/test_orchestrator_consensus.py`

### Implementation for User Story 2

- [X] T025 [US2] Author the Phase 3 tasking prompt (strict linear, dependency-ordered, review criteria per task) in `.skillshare/skills/issue-orchestrator/SKILL.md`
- [X] T026 [P] [US2] Author the Phase 4 analysis-gate prompt (fail-closed; tool-error→missing-input vs findings→gate-block, FR-028) in `.skillshare/skills/issue-orchestrator/SKILL.md`
- [X] T027 [P] [US2] Author the Phase 5 verification-gate prompt (design-intent/functionality/standards; Tier classification; acceptance-criterion = Tier 1, FR-032) in `.skillshare/skills/issue-orchestrator/SKILL.md`
- [X] T028 [US2] Implement `consensus.py` wrapper over `parallel_agent.py` + threshold mapping from `command_config.yml` (FR-034) in `configs/claude/scripts/orchestrator/consensus.py`
- [X] T029 [US2] Wire gate consensus into Phase 4 and Phase 5 dispatch; map verdicts to APPROVED/NEEDS_REVIEW/BLOCKED per `validation_criteria.yml` in `configs/claude/scripts/orchestrator/pipeline.py`
- [X] T030 [US2] Implement implement-approval (P4) and PR-open-approval (P5) gating + `no-automation` re-check before each phase advance (FR-037 mid-pipeline halt) in `configs/claude/scripts/orchestrator/pipeline.py`

**Checkpoint**: US1 + US2 work independently; the two gates bracket code generation.

---

## Phase 5: User Story 3 — Arbitrated Clarification Synthesis (Priority: P2)

**Goal**: Arbitrate between the engine's reasoning and `agy` recommendations using the documented resolution order; log conflicts.

**Independent Test**: Provide an `agy` recommendation conflicting with a repo pattern → repo-consistent option chosen, conflict logged (chosen/rejected/rationale), never silently deferred; `agy` absent → synthesis proceeds.

### Tests for User Story 3 ⚠️ (write first, ensure they FAIL)

- [X] T031 [P] [US3] Contract + integration test: Phase 2 conflict resolution order and `agy`-absent handling in `tests/python/test_orchestrator_phase2.py`

### Implementation for User Story 3

- [X] T032 [US3] Author the Phase 2 clarification-synthesis prompt (resolution order: repo-consistency → modularity/safety → reversibility) in `.skillshare/skills/issue-orchestrator/SKILL.md`
- [X] T033 [US3] Implement `agy`-advisory handling (absence does not block, FR-028 exemption) + conflict logging in `configs/claude/scripts/orchestrator/engine.py`

**Checkpoint**: US1–US3 independently functional.

---

## Phase 6: User Story 4 — Review-Driven PR Resolution (Priority: P2)

**Goal**: Diagnose root cause of review/CI feedback, emit precise modifications, and post a professional PR reply ending in a confirmation marker.

**Independent Test**: Provide review comments + a CI failure log → targeted modifications (file/location/change/addresses), single root-cause statement, reply ending in ✅/🛠️.

### Tests for User Story 4 ⚠️ (write first, ensure they FAIL)

- [X] T034 [P] [US4] Contract + integration test: Phase 6 root-cause modifications + reply-marker enforcement in `tests/python/test_orchestrator_phase6.py`

### Implementation for User Story 4

- [X] T035 [US4] Author the Phase 6 PR-resolution prompt (root-cause not symptom; precise modifications; reply ends ✅/🛠️) in `.skillshare/skills/issue-orchestrator/SKILL.md`
- [X] T036 [US4] Implement PR-feedback ingestion via `git_ops.sh` + reply-marker validation in `configs/claude/scripts/orchestrator/daemon.py`

**Checkpoint**: US1–US4 independently functional; an opened PR can be driven to clean.

---

## Phase 7: User Story 5 — Deterministic, Safe, Auditable Contract (Priority: P3)

**Goal**: Guarantee machine-parseable, reproducible, injection-resistant, conservative behavior with a durable redacted audit trail, retry cap, and resource-pause — across every phase.

**Independent Test**: Malformed input → `blocked` + escalation; embedded "ignore your rules" → ignored + noted; identical input twice → identical structured output; secret in input → redacted in audit; token exhaustion → pause/resume with no attempt increment.

### Tests for User Story 5 ⚠️ (write first, ensure they FAIL)

- [X] T037 [P] [US5] Determinism golden-transcript tests (identical payload → identical envelope, FR-003/SC-002) in `tests/python/test_orchestrator_determinism.py`
- [X] T038 [P] [US5] Redaction fixture-corpus tests (0 unredacted secrets/PII, SC-016) in `tests/python/test_orchestrator_redaction.py`
- [X] T039 [P] [US5] Safety tests: malformed/contradictory → blocked+escalation (FR-005), injection ignored+noted (FR-023), destructive-op withheld (FR-024) in `tests/python/test_orchestrator_safety.py`
- [X] T040 [P] [US5] Retry/pause/escalation tests (2-attempt cap FR-027; transient pause no-attempt-increment FR-035; critical-flag FR-025) in `tests/python/test_orchestrator_retry_pause.py`

### Implementation for User Story 5

- [X] T041 [US5] Implement append-only JSONL audit (skillclaw_audit pattern, `chmod 700` state dir, fail-open) in `configs/claude/scripts/orchestrator/audit.py` (FR-029)
- [X] T042 [US5] Implement redaction (reuse `skillclaw_scrub.py`) as a MANDATORY pre-write hook inside audit.py (FR-038) in `configs/claude/scripts/orchestrator/redact.py`
- [X] T043 [US5] Implement the 2-attempt cap → escalation and the critical-failure-flag → escalation paths (FR-027, FR-025) in `configs/claude/scripts/orchestrator/pipeline.py`
- [X] T044 [US5] Implement resource-pause: transient `blocking_state`, hourly resume poll, no attempt increment, state preserved (FR-035) in `configs/claude/scripts/orchestrator/daemon.py`
- [X] T045 [US5] Implement missing/contradictory-input → blocked+escalation, untrusted-input injection note, and destructive-op guard (FR-005, FR-023, FR-024) in `configs/claude/scripts/orchestrator/engine.py`

**Checkpoint**: All cross-cutting guarantees enforced across every phase.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Deployment, docs, hardening, and end-to-end validation

- [X] T046 [P] Integrate the daemon into `bootstrap.sh` deploy (idempotent, existence-guarded; non-zero exit on unrecoverable failure, Principle V)
- [X] T047 [P] Run `configs/claude/scripts/label_sync.sh` to provision `no-automation` across platforms
- [X] T048 [P] Docs: add orchestrator section to `docs/COMMANDS.md` and `README.md`; note tool policy in `command_config.yml`
- [X] T049 [P] Security hardening: verify `chmod 700` state dir, no secret leakage to stdout/audit, no engine side-effects
- [X] T050 [P] Lint pass: `yamllint configs/claude/config/orchestrator.yml`, `shellcheck` any new shell, JSON-schema parse check in CI
- [X] T051 [P] Deploy the skill via `sync-skills` and verify `/issue-orchestrator` resolves
- [~] T052 Run the `quickstart.md` acceptance walkthrough — **offline validation passed** (76 pytest + 3 bats, contracts parse, daemon dry-run dispatch, SC-001/002/016 confirmed). Full live-LLM end-to-end (real issue → LLM phases → PR; SC-007/012/017) deferred: needs the live engine backend (R1) + `./bootstrap.sh` package home-deploy

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Stories (Phases 3–7)**: All depend on Foundational
  - US1 (P1) and US2 (P1) are the core; US2's gate logic depends only on Foundational, not on US1
  - US3 (P2), US4 (P2), US5 (P3) depend only on Foundational and can proceed in parallel with the P1 stories
- **Polish (Phase 8)**: Depends on all targeted stories being complete

### User Story Dependencies

- **US1**: Foundational only — independently testable (triage recommender)
- **US2**: Foundational only — gates are independently testable with stubbed inputs; `consensus.py` (T028) reuses `parallel_agent.py`
- **US3**: Foundational only — Phase 2 synthesis independently testable
- **US4**: Foundational only — Phase 6 resolution independently testable
- **US5**: Foundational only — cross-cutting guarantees verified per-phase; audit/redaction (T041–T042) should land before a production run but do not block other stories' tests

### Within Each User Story

- Tests written first and FAIL before implementation
- Prompts (skill) + schema wiring before pipeline/daemon integration
- Single-file tasks without [P] are sequential (same file); [P] tasks touch different files

---

## Parallel Opportunities

- All Setup [P] tasks (T002–T006) run in parallel
- Foundational [P] tasks (T010, T011, T013, T014, T015) run in parallel after T007–T009
- Phase-prompt authoring tasks across stories (T026, T027 within US2; prompts across US1/US3/US4/US5) are different sections/files and largely parallelizable
- All per-story test tasks marked [P] run in parallel
- Once Foundational completes, US1–US5 can be staffed in parallel

## Parallel Example: User Story 2

```bash
# Tests first (parallel):
Task: "Contract tests phase 3/4/5 in tests/python/test_orchestrator_phase345_contract.py"
Task: "Integration test gates in tests/python/test_orchestrator_gates.py"
Task: "Consensus threshold mapping test in tests/python/test_orchestrator_consensus.py"

# Then prompts (parallel — distinct skill sections):
Task: "Phase 4 analysis-gate prompt"
Task: "Phase 5 verification-gate prompt"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational)
2. Complete Phase 3 (US1 — prioritization)
3. **STOP and VALIDATE**: a standalone triage recommender that ranks issues and respects `no-automation`
4. Demo if ready

### Incremental Delivery

1. Setup + Foundational → engine↔daemon boundary ready
2. US1 → triage recommender (MVP)
3. US2 → doubly-gated implementation pipeline (the core autonomous loop)
4. US3 → arbitrated clarification; US4 → PR resolution loop
5. US5 → harden determinism/safety/audit across all phases
6. Polish → deploy via bootstrap, docs, end-to-end quickstart validation

### Constitution alignment

- US2's gate consensus (T028) and US5's verification verdicts reuse `command_config.yml` thresholds and `validation_criteria.yml` tiers — no parallel validation logic is created (Principle III/IV)
- `parallel_agent.py` is consumed, never modified (Principle IV)
- All config lands in `configs/` and deploys via `bootstrap.sh` (Principle I, V)

---

## Notes

- [P] = different files, no incomplete dependencies
- Every task names an exact file path; single-file edits are kept sequential to avoid conflicts
- This feature's own PRs require multi-agent cross-verification before merge (Constitution Principle II — security-sensitive + >200 lines)
- Commit after each task or logical group; stop at any checkpoint to validate a story independently
