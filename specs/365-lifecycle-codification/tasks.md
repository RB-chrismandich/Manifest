---
description: "Task list for feature 365 — Codified State-Gated Development Lifecycle"
---

# Tasks: Codified State-Gated Development Lifecycle

**Input**: Design documents from `/specs/365-lifecycle-codification/`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓ (lifecycle-cli, provider-mapping, verify-and-specreview)

**Tests**: INCLUDED. The orchestrator is safety-gate logic; the repo convention (specs 360/361) is bats-tested shell helpers with a pure decide core. TDD applies to the decide core especially.

**Organization**: by user story (US1–US5) for independent implementation/testing. Shell-first; paths per plan.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1–US5; Setup/Foundational/Polish carry no story label

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Create `configs/claude/scripts/lifecycle.sh` skeleton: shebang, `set -euo pipefail`, `err()` helper, `--help` (≤15 lines, exits 0 BEFORE any state/dependency lookup), subcommand dispatch stub (`init|status|decide|gate|advance|anchor|regress`)
- [X] T002 [P] Create `configs/claude/config/lifecycle_providers.yml` scaffold (provider keys github/gitlab/linear/jira; empty `tier_map`/`status_map`/`missing_tier_behavior`/`access` sections per contracts/provider-mapping.md)
- [X] T003 [P] Create bats scaffolds `tests/bats/lifecycle.bats` and `tests/bats/spec_review_mode.bats` (load helpers, temp `LIFECYCLE_STATE_DIR`, seam env stubs)
- [X] T004 [P] Add `lifecycle.sh` + `lifecycle_providers.yml` to bootstrap deploy verification (confirm `configs/claude/scripts/` + `config/` are deployed by `bootstrap.sh` to `~/.claude/`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: the decide core + state store + entry detection block ALL user stories.

- [X] T005 Write FAILING bats for the pure `decide` core in `tests/bats/lifecycle.bats`: skip-detection (agent→refuse, human→warn, names missing_prereq), gate evaluation per gate_type (verdict/runner/coverage/artifact), and **fail-closed** on malformed input (→refuse) — per contracts/lifecycle-cli.md decision rules
- [X] T006 Implement `lifecycle.sh decide <signals-json>` (embedded `python3 -c`, always exit 0, deterministic, no I/O) to pass T005; add `gate` alias that maps decide→non-zero exit for loop callers
- [X] T007 Implement state persistence layer in `lifecycle.sh` (StateManager pattern): `${MANIFEST_STATE_ROOT:-$HOME/.manifest}/lifecycle/state/<track-id>.json` where **`track-id` ≡ `<provider>__<sanitized-entity-id>`** (single definition in contracts/lifecycle-cli.md + data-model.md; matches plan.md Storage), `0700`/`0600`, atomic temp+mv, secret redaction; seam `LIFECYCLE_STATE_DIR`
- [X] T008 [P] Implement entry-point detection (provider+entity_id+tier classification) shared by `init`, extending `git_platform.sh`-style patterns for github/gitlab/linear/jira in `configs/claude/scripts/lifecycle.sh` (or a sourced helper); unrecognized → error, no track (FR-019)
- [X] T009 Encode the Lifecycle Definition (9 phases → ordered command(s), entry/exit/gate_type) as data read by `lifecycle.sh` (inline assoc-array or `lifecycle_providers.yml` sibling); single source for phase order

**Checkpoint**: pure gate + state + entry detection ready.

---

## Phase 3: User Story 1 — Run the lifecycle without skipping phases (P1) 🎯 MVP

**Goal**: drive a track through 9 phases in order; skips refused (agent) / warned (human); status inspectable.
**Independent Test**: `init` a track, `advance` phase-by-phase, attempt a skip → refused with prerequisite named, `status --json` shows phase/completed/outstanding.

- [X] T010 [P] [US1] Write FAILING bats: `init`/`status`/`advance` happy path, skip→refuse(agent)+warn(human), `regress --to --reason` (logged), `anchor` re-emit, resume from persisted state (`tests/bats/lifecycle.bats`)
- [X] T011 [US1] Implement `lifecycle.sh init <entry-point>` (create Track, set `current_phase=specify`, persist; idempotent re-init) (FR-003, FR-019)
- [X] T012 [US1] Implement `lifecycle.sh advance <track-id>` (compute current phase gate signal → call `decide` → persist next phase on `allow`, exit 1 on refuse, exit 3 on warn) (FR-004). Phases 1–7 advance once at the Task tier; **phases 8–9 are a two-level iterator (FR-028)**: the Task holds at Implement/Verify while each child Sub-Task independently transitions through its own Implement→Verify sub-state, and the Task advances to `done` only when every Sub-Task is complete-or-exempt. Bats (T010) MUST cover the multi-Sub-Task hold/advance.
- [X] T013 [US1] Implement `lifecycle.sh status [--json]` (current_phase, completed_phases, outstanding gates) (FR-007) and `anchor` (FR-006)
- [X] T014 [US1] Implement `lifecycle.sh regress --to <phase> --reason <text>` (append regression_log, re-enter earlier phase; reject missing reason exit 2) (FR-005)
- [X] T015 [US1] Create `.skillshare/skills/lifecycle/SKILL.md`: phase→command map (Specify=/speckit-specify … Verify=/speckit-implement-review+smoke), `actor_mode` default human (advisory) vs agent (hard), invokes the mapped command then `lifecycle.sh advance` (FR-001, FR-006). Spec-Review product (phase 3) vs technical (phase 7) MUST pass an explicit mode identifier per FR-002 — using the `--mode` flag from T036 (pulled into MVP, see below); until that flag exists T015 sets the `SPEC_REVIEW_TEMPLATE`/`SPEC_REVIEW_STATE` env seams directly
- [X] T016 [US1] Add `tool_policies` entry for `/lifecycle` in `configs/claude/config/command_config.yml`

**Checkpoint**: US1 independently functional — the codified, gated lifecycle works for one provider with no hierarchy/Jira yet.

---

## Phase 4: User Story 2 — Verify task-by-task backed by the smoke orchestrator (P1)

**Goal**: Implement appends per-workflow smoke tests; Verify runs them at Lite as the completion gate; missing coverage fails.
**Independent Test**: ship a workflow → smoke test appended; Verify passes only when present+green; remove it → gate fails (EMPTY≠pass).

- [X] T017 [P] [US2] Write FAILING bats (seam `LIFECYCLE_SMOKE_CMD` stub returning canned exit codes / `list --json`): Implement-exit coverage reconciliation OK vs MISSING, Verify gate exit 0/1/2 mapping (2=EMPTY→refuse), exemption path (`tests/bats/lifecycle.bats`)
- [X] T018 [US2] Implement Implement-phase exit criterion: diff track `shipped_workflow_ids` vs `smoke_test.py list --app <unit> --json`; absent+non-exempt → `coverage=MISSING` (blocks advance) (FR-008, FR-010)
- [X] T019 [US2] Implement exemption handling in track state (`subtask_states[].exempt`+`exempt_reason`, required when exempt) (FR-011)
- [X] T020 [US2] Implement Verify-phase gate: `smoke_test.py run --app <unit> --tier Lite --junit <path>`, gate on exit code (0 allow / 1,2 refuse-agent) via `decide` gate_type=runner (FR-009, FR-012)
- [X] T021 [US2] Map per-Sub-Task coverage traceability from JUnit `<testcase>` ids into `subtask_states[].coverage_workflow_ids` (FR-011); document that critical-path tests must be tier Lite

**Checkpoint**: US1+US2 — a unit cannot reach done without passing Lite smoke coverage for each user-facing workflow.

---

## Phase 5: User Story 3 — Four-tier hierarchy across providers (P2)

**Goal**: represent/navigate Initiative→Epic→Task→Sub-Task; provision top-down; missing tier → config error; partial failure → no orphaned local state.
**Independent Test**: build a 4-tier tree on a supporting provider; request a missing tier → error naming it; simulate child-failure → FAILED_PROVISION, no orphan.

- [X] T022 [P] [US3] Write FAILING bats: tier→construct resolution, missing-tier→config error (FR-014), top-down order, partial-provision→FAILED_PROVISION+flag (FR-016), and **retry-after-partial-failure asserts NO duplicate entities created (FR-022 create-or-adopt)**
- [X] T023 [US3] Populate `lifecycle_providers.yml` `tier_map` for all 4 providers + `missing_tier_behavior` (default error) per contracts/provider-mapping.md
- [X] T024 [US3] Implement Hierarchy Node model + persistence (node_id/external_id/provider_type/tier_level/parent_node_id/status/provision_state/remote_recorded_id) in track state (FR-013, FR-017)
- [X] T025 [US3] Implement top-down provisioning (obtain parent external_id before children). **Delegate the Task/Sub-Task issue-creation leg to `/speckit-taskstoissues` (do not reimplement it, FR-001)**; `lifecycle.sh` wraps it to add the higher tiers (Initiative/Epic) and non-GitHub providers (`linear_ops.sh create-sub-issue`, Jira MCP) plus FAILED_PROVISION/rollback handling. **Create-or-adopt idempotency (FR-022)**: lookup-before-create / dedup by external_id so a retry after `FAILED_PROVISION` adopts the existing node instead of duplicating it. Partial failure → mark FAILED_PROVISION, record remote id, halt subtree, flag reconciliation (FR-016)
- [X] T026 [US3] Implement tier classification + missing/renamed-tier configuration error (naming the unresolved tier) during entry + provisioning (FR-014)
- [X] T027 [US3] Record lifecycle artifacts at correct tier (scope@Initiative/Epic, design@Task, impl/verify@Sub-Task) in track `hierarchy_ref` (FR-015, FR-028)

**Checkpoint**: hierarchy works on GitHub/GitLab/Linear.

---

## Phase 6: User Story 4 — Jira as a tracked provider via pre-auth MCP (P2)

**Goal**: enter from a Jira URL/key; fetch via MCP; classify tier; transitions via MCP; same lifecycle as other providers.
**Independent Test**: Jira key + URL recognized; entity fetched via MCP (no bespoke auth); tier classified; status applied via transition id; identical phase flow.

- [X] T028 [P] [US4] Write FAILING bats (seam stub for the MCP/jira call layer): Jira entry-point detection (key + browse URL), tier classification from issue-type metadata, transition-id (not free-text) status application
- [X] T029 [US4] Wire the `atlassian` MCP server (already in `mcp_servers.yml`) into `configs/claude/settings.local.json` (FR-020)
- [X] T030 [US4] Jira routing = `--external-id` adopt seam + `status-map` (shell) PLUS an agent-orchestrated MCP flow (read `getJiraIssue`/`searchJiraIssuesUsingJql`, tier `getJiraProjectIssueTypesMetadata`, transition `getTransitionsForJiraIssue`+`transitionJiraIssue`, provision `createJiraIssue`) documented in SKILL.md — MCP is an agent-layer capability, not shell-callable (FR-018, FR-020, FR-021)
- [X] T031 [US4] Add Jira `status_map` (canonical→transition id, resolved at runtime) + `tier_map` (Initiative=Advanced Roadmaps, Epic/Story/Sub-task) + `access: mcp` to `lifecycle_providers.yml`
- [X] T032 [US4] Verify the same `/lifecycle` flow runs unchanged on a Jira entry point (SC-004) — only provider/entry differ

**Checkpoint**: all four providers (GitHub/GitLab/Linear/Jira) drive the identical lifecycle.

---

## Phase 7: User Story 5 — Govern & enforce over time (P3)

**Goal**: rules codified in the constitution (single source); autodev loop enforces gates (never merges past failing gate); drift detectable.
**Independent Test**: amend constitution + dependent docs consistent; run loop on a failing-Verify unit → halts + needs-human, no merge.

- [X] T033 [US5] Amend `.specify/memory/constitution.md` via `/speckit-constitution`: add Principle VI (State-Gated Lifecycle) + "## Development Lifecycle" section (phase→command table, gating, 4-tier+FR-028, provider abstraction→config, Verify-smoke gate, verdict reuse), bump MINOR → v1.1.0, update Sync Impact Report (FR-023, research D7)
- [X] T034 [P] [US5] Sync dependent templates: `.specify/templates/plan-template.md` (Constitution Check adds lifecycle gates) and `.specify/templates/tasks-template.md` (lifecycle-gated smoke-coverage task category; scope, don't blanket-mandate tests)
- [X] T035 [P] [US5] Update `docs/SPEC-SYSTEMS.md` to describe the canonical 9-phase state-gated lifecycle (replace the old spec→…→implement description)
- [X] T036 [US5] Add `--mode product|technical` to `configs/claude/scripts/spec_review.sh` (sugar over `SPEC_REVIEW_TEMPLATE`/`SPEC_REVIEW_STATE`; default unchanged; `--help` before deps; `err()`); make T037 pass. **⬆️ MVP-blocking (FR-002): complete during the MVP increment alongside T015 — listed here for US5 traceability but sequenced into Phase 3.** Until done, T015 uses the env seams directly.
- [X] T037 [P] [US5] Write bats `tests/bats/spec_review_mode.bats`: `--mode` routes template/state, default behavior unchanged, `--help` succeeds in clean env. **⬆️ MVP-blocking — sequence with T036.**
- [X] T038 [US5] Implement review-gate verdict parsing in `lifecycle.sh` (spec-review `--format json`: []→APPROVED, findings→NEEDS_REVIEW/BLOCKED by severity; optional `parallel_agent.py --validate` consensus) → `decide` gate_type=verdict (FR-027)
- [X] T039 [US5] Wire autodev enforcement: `configs/claude/scripts/auto_issue_dev.sh` + `pr_merge_loop.sh` call `lifecycle.sh gate` before advancing/merging; refuse→halt+`needs-human`; never merge past failing gate (FR-024, SC-011)
- [X] T040 [US5] Implement loop-safe status reconciliation (shadow-compare + origin suppression) in the loop using `tracker_shadow`; canonical→provider via `status_map`; idempotent (FR-021, FR-022, SC-010). Bats MUST assert re-applying an already-set label/transition is a no-op (FR-022 idempotency)
- [X] T041 [US5] Implement drift detection (`lifecycle.sh status` / an audit subcommand surfaces skipped phase, missing required coverage, stale state) (FR-026)

**Checkpoint**: governed + enforced end-to-end.

---

## Phase 8: Polish & Cross-Cutting

- [X] T042 [P] Run `./bootstrap.sh` redeploy; verify deployed `~/.claude/scripts/{lifecycle.sh,spec_review.sh}` match repo (resolve deployed-vs-repo drift) (research D6 risk)
- [X] T043 [P] Update `docs/COMMANDS.md` (add `/lifecycle`) and `AGENTS.md`/`configs/claude/CLAUDE.md` runtime guidance
- [X] T044 [P] Verify `configs/claude/config/validation_criteria.yml` has no drift vs the reused verdict model; add per-command overrides for product/technical spec-review + analyze gates if needed
- [X] T045 Run `shellcheck configs/claude/scripts/lifecycle.sh spec_review.sh` + `yamllint configs/claude/config/lifecycle_providers.yml`; fix findings
- [X] T046 Execute `quickstart.md` end-to-end against one provider (smoke validation of SC-001..SC-011)
- [X] T047 [P] Confirm `.specify/extensions.yml` phase hooks remain consistent with the codified phase→command map

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** blocks all stories (decide core T006, state T007, entry T008, definition T009 are universal prereqs).
- **US1 (P1)** depends only on Foundational → MVP.
- **US2 (P1)** depends on US1 (advance/state) — extends advance with coverage/verify gates.
- **US3 (P2)** depends on Foundational + US1 (track/provisioning); independent of US2.
- **US4 (P2)** depends on US3 (provider seam + tier model) — adds Jira routing.
- **US5 (P3)** depends on US1–US4 existing (constitution describes them; loop enforces them).
- **Polish (P8)** after desired stories.

### Parallel opportunities
- Setup T002/T003/T004 [P]; Foundational T008 [P] alongside T005-T007 core.
- Within a story, the FAILING-test task runs first; `[P]` tasks touch different files.
- US3 and US2 can proceed in parallel after US1 (different files: hierarchy vs verify).

---

## Implementation Strategy

**MVP** = Phase 1 + 2 + US1 (T001–T016): a working, gated, single-provider lifecycle. STOP and validate skip-refusal + status before extending.

**Increment 2** = US2 (Verify smoke gate) — the headline alignment; deploy/demo.

**Increment 3** = US3 + US4 (hierarchy + Jira) — multi-provider.

**Increment 4** = US5 (governance + autodev enforcement) — makes it durable; requires bootstrap redeploy (T042) since `spec_review.sh`/`lifecycle.sh` are deployed scripts.

## Notes
- Commit after each task or logical group; the decide core (T005/T006) is the load-bearing safety contract — do not merge it without green bats.
- `[P]` = different files, no incomplete dependency. Avoid same-file conflicts (most of `lifecycle.sh` is one file → those tasks are sequential).
- Tests fail before implementation (TDD) for the decide core and gates especially.
