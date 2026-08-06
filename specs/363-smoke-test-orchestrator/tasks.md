# Tasks: Smoke Test Orchestrator

**Input**: Design documents from `specs/363-smoke-test-orchestrator/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included. This feature *is* a test framework, the plan enumerates specific test files, and the constitution's Tier-2 gate expects coverage — so each story is test-first.

**Organization**: Tasks are grouped by user story (priority order) so each is independently implementable and testable.

## Path Conventions

Single project. Engine package: `configs/claude/scripts/smoke_orchestrator/`. CLI shim: `configs/claude/scripts/smoke_test.py`. Skill: `.retired skill supply/skills/smoke-orchestrator/`. Catalog: `smoke-catalog/`. Tests: `tests/python/smoke_orchestrator/`, `tests/bats/`.

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Create package skeleton `configs/claude/scripts/smoke_orchestrator/` with `__init__.py`, `__main__.py`, and `steps/__init__.py`
- [X] T002 Add `tests/requirements-smoke.txt` (playwright, pyyaml) and create `tests/python/smoke_orchestrator/` + `tests/python/smoke_orchestrator/fixtures/`
- [X] T003 [P] Vendor contract schemas into the package: copy `specs/363-smoke-test-orchestrator/contracts/*.json` → `configs/claude/scripts/smoke_orchestrator/schemas/` for runtime validation
- [X] T004 [P] Build test fixtures in `tests/python/smoke_orchestrator/fixtures/`: a tiny local HTML page, a stub HTTP server, a trivial CLI script, and sample `billing.yaml` catalog

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [X] T005 Implement dataclasses (Catalog, TestDefinition, Step, Tier, StateValue, RunReport) in `configs/claude/scripts/smoke_orchestrator/models.py`
- [X] T006 Implement internal validation helpers (`validate_catalog`, `validate_workflow` enforcing the vendored schema rules; no jsonschema dep) in `configs/claude/scripts/smoke_orchestrator/validation.py`
- [X] T007 Implement catalog I/O (locate `smoke-catalog/<app>.yaml`, load+validate YAML, atomic write via tempfile+`os.replace`, per-app `fcntl.flock` helper) in `configs/claude/scripts/smoke_orchestrator/catalog.py`
- [X] T008 [P] Implement `Redactor` (register sensitive values, scrub strings) in `configs/claude/scripts/smoke_orchestrator/redact.py`
- [X] T009 [P] Implement `StateManager` core (in-memory store, `${state.*}`/`${env.*}` resolution, sensitive env-only with raise-if-missing) in `configs/claude/scripts/smoke_orchestrator/state.py`
- [X] T010 Implement Tier ordering + cumulative selection predicate (`tier_rank`, `select(max_rank)`) in `configs/claude/scripts/smoke_orchestrator/models.py`

---

## Phase 3: User Story 1 — Agent appends a smoke test (Priority: P1) 🎯 MVP

**Goal**: An agent submits a structured workflow description and the central catalog gains a valid, tier-tagged, idempotent entry.
**Independent Test**: Submit a new workflow → one well-formed entry added, existing untouched, catalog still parses; resubmit same `id` → updated, not duplicated.

- [X] T011 [P] [US1] Write `tests/python/smoke_orchestrator/test_appender.py`: idempotent upsert (10× → 1 entry, SC-002), invalid-input rejection leaves catalog unchanged (FR-003), concurrent append safety (FR-015)
- [X] T012 [US1] Implement `SmokeTestAppender.append()` (validate → per-app lock → upsert-by-id → atomic write) in `configs/claude/scripts/smoke_orchestrator/appender.py`
- [X] T013 [US1] Wire CLI `append` (`--from`, `--stdin`, `--dry-run`, exit 0/1/2) in `configs/claude/scripts/smoke_orchestrator/cli.py`
- [X] T014 [US1] Run `test_appender.py` green and confirm the US1 independent test (append twice → single entry)

---

## Phase 4: User Story 2 — Run the suite filtered by tier (Priority: P1) 🎯 MVP

**Goal**: Run the catalog selecting a tier, get a per-test report, a verdict, and a gating exit code.
**Independent Test**: Mixed-tier catalog; `run --tier Lite` runs only Lite; exit non-zero iff a selected test failed; empty tier reported distinctly.

- [X] T015 [P] [US2] Write `tests/python/smoke_orchestrator/test_executor_tiers.py`: cumulative selection (Lite⊆Full⊆Full+Extra, FR-006), empty-selection distinct from pass (FR-008), exit codes 0/1/2, and a mixed UI+API+CLI fixture catalog confirming all three step types dispatch end-to-end (SC-009)
- [X] T016 [P] [US2] Implement step runners `steps/ui.py` (Playwright Page), `steps/api.py` (APIRequestContext), `steps/cli.py` (subprocess arg-array, no `shell=True`) under `configs/claude/scripts/smoke_orchestrator/steps/`
- [X] T017 [US2] Implement `SmokeTestExecutor.run()` (cumulative filter, per-test loop, per-step timeout with no auto-retry, shared Playwright context) in `configs/claude/scripts/smoke_orchestrator/executor.py`
- [X] T018 [US2] Implement `report.py` (JUnit XML via `xml.etree.ElementTree` + console summary + verdict/exit_code incl. EMPTY) in `configs/claude/scripts/smoke_orchestrator/report.py`
- [X] T019 [US2] Wire CLI `run` (`--app`, `--tier`, `--junit`, `--base-url`) in `configs/claude/scripts/smoke_orchestrator/cli.py`
- [X] T020 [US2] Run `test_executor_tiers.py` green and confirm the US2 independent test (Lite excludes Full; non-zero on failure)

---

## Phase 5: User Story 3 — Chain tests and pass state (Priority: P2)

**Goal**: A downstream step consumes a named value produced upstream, in-memory during a run and optionally persisted across runs; missing state blocks (never silently passes).
**Independent Test**: Two-step chain where A emits an id and B references it → B gets A's runtime value; with persistence, a later run reuses it; missing upstream → B blocked.

- [X] T021 [P] [US3] Write `tests/python/smoke_orchestrator/test_chaining_state.py`: downstream receives real upstream value; missing-state → blocked + cascade AND a non-zero run verdict (FR-011, never a false pass); persisted reuse across runs
- [X] T022 [P] [US3] Write `tests/python/smoke_orchestrator/test_secret_safety.py`: no sensitive value in JUnit XML, console, or persisted state (SC-006)
- [X] T023 [US3] Implement captures extraction (JSONPath/api, selector/ui, regex/cli) + `needs`/blocked-cascade evaluation in `configs/claude/scripts/smoke_orchestrator/executor.py`
- [X] T024 [US3] Implement persisted state scope (`$MANIFEST_STATE_ROOT/smoke/state/<app>.json`, non-secret only) and opt-in per-step `retry` in `configs/claude/scripts/smoke_orchestrator/state.py` and `executor.py`
- [X] T025 [US3] Integrate `Redactor` into every output sink (report + logs) in `configs/claude/scripts/smoke_orchestrator/report.py`
- [X] T026 [US3] Run `test_chaining_state.py` and `test_secret_safety.py` green; confirm the US3 independent test

---

## Phase 6: User Story 4 — Catalog lifecycle (Priority: P3)

**Goal**: Inspect coverage and keep the catalog honest (update-in-place, prune).
**Independent Test**: Append a workflow, append again with changes, list → one updated entry with correct tier/step count.

- [X] T027 [P] [US4] Write `tests/python/smoke_orchestrator/test_lifecycle.py`: coverage listing, prune-by-id, update-in-place reporting
- [X] T028 [US4] Implement `list` command (per-workflow id/tier/step-count, `--json`, FR-014) in `configs/claude/scripts/smoke_orchestrator/cli.py`
- [X] T029 [US4] Implement prune/remove-by-id (idempotent on absent id, FR-018) in `configs/claude/scripts/smoke_orchestrator/appender.py` + `prune` CLI subcommand in `cli.py`
- [X] T030 [US4] Run `test_lifecycle.py` green; confirm the US4 independent test (append+update → single listed entry)

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T031 [P] Author `.retired skill supply/skills/smoke-orchestrator/SKILL.md` (when to append after shipping a feature; how to run `Lite`/`Full`; trigger phrases) — keep frontmatter within `context_budget`
- [X] T032 [P] Create executable shim `configs/claude/scripts/smoke_test.py` (dispatch to `smoke_orchestrator.cli`; `--help` succeeds before any dependency lookup; `chmod +x`; `err()` convention)
- [X] T033 [P] Write `tests/bats/smoke_orchestrator_cli.bats`: `--help` exits 0 with Usage, exit codes 0/1/2, skill wrapper present
- [X] T034 Add idempotent opt-in install of smoke deps (Chromium-only `playwright install chromium`, existence-guarded) to the bootstrap/CI smoke path
- [X] T035 [P] Register `smoke-orchestrator` in `configs/claude/config/command_config.yml` `tool_policies`, then regenerate cursor rules (`generate_cursor_rules.sh`)
- [X] T036 [P] Regenerate `docs/COMMANDS.md` + GEMINI.md/AGENTS.md index via `configs/claude/scripts/generate_commands_doc.py --inject-guides`
- [X] T037 Run the full repo gate (`/pr-regression-smoke`) — shellcheck/yamllint/markdownlint/drift/bats/pytest + smoke — and make it green
- [X] T038 Run `parallel_agent.py` Tier-1 cross-verification (focus: shell-injection in CLI steps, secret leakage, error handling) per Constitution II/III before merge
- [X] T039 [P] Verify SC-003 performance budget: a representative `Lite` run over the fixture catalog completes in < 2 minutes; assert wall-clock in `tests/python/smoke_orchestrator/test_executor_tiers.py` (or a dedicated perf marker)

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational)** block everything.
- **US1 (P1)** and **US2 (P1)** depend only on Foundational and are the **MVP**. They can proceed in parallel after Phase 2 (different files: `appender.py` vs `executor.py`/`report.py`/`steps/`), converging only in `cli.py` (T013 vs T019 — sequence those two).
- **US3 (P2)** depends on US2's executor (extends `executor.py`) + Foundational state/redactor.
- **US4 (P3)** depends on US1's appender + catalog I/O.
- **Phase 7** runs after the stories it documents/tests; T037–T038 are the final gates.

```text
Setup → Foundational ─┬─ US1 (appender) ──────────────┐
                      ├─ US2 (executor/tiers) ─ US3 (chaining/state)
                      └────────────────────────────────┴─ US4 (lifecycle) → Polish → gates
```

## Parallel Execution Examples

- After Phase 2: run **T011 [US1]** and **T015/T016 [US2]** test+runner tasks in parallel (distinct files).
- Within Foundational: **T008 (Redactor)** ∥ **T009 (StateManager)** (distinct files).
- Polish: **T031 (skill)** ∥ **T032 (shim)** ∥ **T033 (bats)** ∥ **T035/T036 (drift regen)**.

## Implementation Strategy

- **MVP = US1 + US2** (both P1): an agent can append a test and a tier-filtered run gates a PR. Ship this first; it satisfies SC-001, SC-002, SC-003, SC-004, SC-007, SC-009 (three target shapes via the step runners). (SC-008 coverage inspection is delivered later in US4 — see Increment 3.)
- **Increment 2 = US3**: chaining + secret-safe state (SC-005, SC-006) — the differentiator from a flat checklist.
- **Increment 3 = US4**: lifecycle/coverage hygiene (satisfies SC-008 — coverage inspection).
- Each story ends with a "verify independent test" task so the increment is demonstrably done before moving on.
- Do not open the PR until **T037** (repo gate green) and **T038** (parallel-agent Tier-1 review) pass — constitution-mandated for this security-sensitive feature.
