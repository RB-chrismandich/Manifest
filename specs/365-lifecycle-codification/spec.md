# Feature Specification: Codified State-Gated Development Lifecycle

**Feature Branch**: `365-lifecycle-codification`

**Created**: 2026-06-28

**Status**: Draft

**Input**: User description: "Review the Gemini discussion ('Jira Integration for Issue Hierarchy') and align the direction forward with our smoke test framework to codify it within our process." The discussion converged on: (1) a strict nine-phase, state-gated development lifecycle — Specify → Clarify → Spec-Review → Plan → Task Creation → Analyze → Spec-Review (technical) → Implement → Verify task-by-task — with hard gating so phases cannot be skipped; (2) a four-tier issue hierarchy — Initiative → Epic → Task → Sub-Task — abstracted polymorphically across issue trackers; and (3) adding Jira (via pre-authenticated MCP, entered from a ticket URL/issue key) as a provider alongside the existing GitHub/GitLab/Linear support. This feature codifies that lifecycle as governed repository process and wires the existing smoke-test orchestrator in as the "Verify task-by-task" gate.

## Clarifications

### Session 2026-06-28

- Q: Scope — codify the lifecycle only, the Jira/hierarchy only, or both in one spec? → A: Both, in one comprehensive spec (lifecycle codification is the spine; the multi-provider four-tier hierarchy and Jira are the supported "direction forward").
- Q: Which issue-tracking providers must the codified lifecycle and four-tier hierarchy support now? → A: All four — GitHub, GitLab, Linear (existing), and Jira (new).
- Q: What does "codify it within our process" mean concretely? → A: Both a project constitution capturing the phases/gating/hierarchy as governing rules **and** a thin lifecycle orchestrator that drives the existing commands with hard state-gating, enforced inside the autonomous-development loop.
- Q: Does the system create the four-tier hierarchy, consume an existing one, or both? → A: Both — consume the existing entry entity (from the ticket URL/issue key) and provision only the missing descendant tiers top-down (never recreating existing ancestors).
- Q: Who is bound by hard state-gating, and how strict is it for human-driven work? → A: Hard halt for the autonomous loop (agents cannot skip); advisory warning with a logged override for human-driven work.
- Q: At what granularity is smoke coverage required before a unit of work can complete? → A: Per user-facing workflow (≥1 passing smoke test each); Sub-Tasks with no user-facing surface are explicitly marked exempt.
- Q: What makes a review/analysis gate pass so the lifecycle can advance? → A: Reuse the constitution's verdict model — advance on APPROVED (Tier-1 pass + Tier-2 ≥0.60 / consensus ≥80%), warn on NEEDS_REVIEW, halt on BLOCKED.

### Spec-Review resolutions 2026-06-28 (agy)

An independent `agy` spec-review surfaced six consistency gaps; all are resolved in this revision:

- **Phase→command cardinality** (FR-001, FR-002): a phase maps to one *or more* ordered commands with individual pass/fail semantics — not strictly 1:1.
- **Lifecycle-track granularity** (FR-028): a track is anchored at the Task tier; phases 1–7 run once at the Task/ancestor tiers, phases 8–9 iterate per Sub-Task.
- **Smoke authorship vs. registration** (FR-008): the implementer authors the test via the orchestrator's existing append operation; the Implement exit criteria only *validates* its existence (no auto-generation).
- **PR-opening vs. gating** (FR-024): opening a draft PR is the mechanism for *entering* Verify; the prohibition applies to merge / mark-complete, not PR creation.
- **Remote-entity rollback** (FR-016, US3-AS4, edge cases): rollback is local-only (`FAILED_PROVISION` + reconciliation); transactional deletion across remote provider APIs is not promised.
- **Dual Spec-Review passes** (FR-002): the product (Phase 3) and technical (Phase 7) passes invoke `/spec-review` with an explicit pass/mode identifier and distinct exit criteria.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a feature through the codified lifecycle without skipping phases (Priority: P1)

A contributor (human or agent) starts a unit of work from a tracker entry and drives it through the nine canonical phases in order. The lifecycle declares the active phase at every step, each phase maps to one existing repository command, and any attempt to jump ahead (for example, writing implementation code while still in Clarify) is refused with a clear message naming the unmet prerequisite. The current phase and outstanding gates are inspectable at any time.

**Why this priority**: This is the core value — turning an informal sequence of commands into an enforced, observable lifecycle. Without it the rest of the system has no backbone. It is independently valuable even before the hierarchy or Jira work lands, because it makes any single feature's progression honest and resumable across separate sessions.

**Independent Test**: Begin a lifecycle track, advance it phase by phase confirming the active phase is announced and the correct command runs at each phase, then attempt to skip a phase and confirm the action is refused with the prerequisite named; finally query the track and confirm it reports current phase, completed phases, and remaining gates.

**Acceptance Scenarios**:

1. **Given** a new lifecycle track at the first phase, **When** each phase's exit criteria are satisfied in order, **Then** the track advances one phase at a time and the active phase is declared at the start of each step.
2. **Given** a track in an early phase (e.g., Clarify), **When** an actor requests a later-phase action (e.g., generate implementation code), **Then** the action is refused with a state-violation message that names the missing prerequisite phase(s) and the track does not advance.
3. **Given** a track at any phase, **When** its status is queried, **Then** the response reports the current phase, the phases already completed, and the gates still outstanding.
4. **Given** a later phase reveals a defect rooted in an earlier phase, **When** a backward transition is requested, **Then** the regression is permitted only when explicitly logged with a reason, and the prior phase is re-entered rather than silently patched forward.
5. **Given** a track resumed in a new session after context is lost, **When** work continues, **Then** the persisted phase is re-anchored and progression continues from the correct phase.

---

### User Story 2 - Verify task-by-task is backed by the smoke-test orchestrator (Priority: P1)

As a unit of work is implemented, coverage grows with it: each user-facing workflow shipped during Implement adds or updates a smoke test in the central catalog. The Verify phase then runs the smoke suite at the critical-path tier as the gate — a unit of work cannot be marked complete unless its smoke coverage exists and passes. Missing coverage is treated as a failure, never as a pass.

**Why this priority**: This is the explicit alignment the request asks for — codifying the smoke-test framework as the lifecycle's verification spine. It is the other half of the MVP: a lifecycle whose final gate is real, executable, and honest about missing coverage. It builds directly on the already-implemented smoke-test orchestrator.

**Independent Test**: Ship a workflow during Implement and confirm a tier-tagged smoke test is appended/updated for it; run Verify and confirm the suite executes at the critical-path tier and the track only completes on a passing verdict; then remove the coverage and confirm Verify fails the gate (missing coverage ≠ pass).

**Acceptance Scenarios**:

1. **Given** a Sub-Task whose implementation ships a user-facing workflow, **When** Implement completes, **Then** a corresponding smoke test for that workflow exists in the catalog (newly appended or updated in place, never duplicated).
2. **Given** a unit of work entering Verify, **When** the Verify gate runs, **Then** the smoke suite executes filtered to at least the critical-path tier and a non-zero verdict (failed, blocked, or empty/no-coverage) prevents the unit from being marked complete.
3. **Given** a shipped workflow with no smoke coverage, **When** Verify runs, **Then** the gate reports missing coverage as a failure distinct from "all passed," so the gap cannot pass silently.
4. **Given** a completed unit of work, **When** its verification is inspected, **Then** each verified Sub-Task is traceable to the smoke test(s) that exercised it.

---

### User Story 3 - Track work in a four-tier hierarchy across providers (Priority: P2)

Work is organized as Initiative → Epic → Task → Sub-Task, independent of which tracker backs it. Lifecycle artifacts live at the correct tier (macro scope at the Initiative/Epic, technical design at the Task, implementation and per-task verification at the Sub-Task). The hierarchy is provisioned top-down so each parent exists before its children, and a tracker that lacks or renames a required tier surfaces a configuration error rather than a silent mismapping.

**Why this priority**: The hierarchy is the structural "direction forward" the discussion settled on. It is high value for organizing multi-tier work and mapping the lifecycle onto where artifacts belong, but the lifecycle and verify gate (US1/US2) already deliver a usable MVP without it.

**Independent Test**: Define an Initiative with a child Epic, Task, and Sub-Task on a provider that supports all tiers; confirm each abstract tier maps to the provider's native construct, that artifacts are recorded at the correct tier, and that requesting a tier the target lacks yields a configuration error instead of a wrong mapping.

**Acceptance Scenarios**:

1. **Given** an abstract four-tier hierarchy, **When** it is represented on a supported provider, **Then** each tier maps to that provider's native construct and parent↔child navigation is possible in both directions.
2. **Given** a hierarchy to provision, **When** it is created, **Then** creation proceeds top-down with each parent's identifier obtained before its children are created.
3. **Given** a target tracker missing or renaming a required tier, **When** the hierarchy is mapped, **Then** a configuration error is surfaced (with the unresolved tier named) rather than a silent or incorrect mapping.
4. **Given** a partial provisioning failure (a parent is created but a child fails), **When** the failure is handled, **Then** local state leaves no orphaned node — the failed node is marked `FAILED_PROVISION` with any remote identifier recorded and flagged for reconciliation — rather than silently continuing with a corrupt tree.

---

### User Story 4 - Add Jira as a tracked provider entered from a ticket URL or issue key (Priority: P2)

A contributor kicks off work by handing the system a Jira ticket URL or issue key. The system detects the provider, fetches the entity via the pre-authenticated MCP, classifies it into one of the four tiers, and bootstraps a lifecycle track — all without bespoke credential handling. Jira joins GitHub, GitLab, and Linear under the same provider-agnostic abstraction, including status-transition mapping that uses Jira's workflow transitions rather than free-text status strings.

**Why this priority**: Jira is the new integration the discussion targets and the entry point that makes the lifecycle usable for Jira-tracked teams. It depends on the hierarchy abstraction (US3) and the lifecycle (US1) being in place, so it follows them.

**Independent Test**: Provide a Jira issue key and a Jira ticket URL; confirm each is recognized as the Jira provider, the entity is fetched via the pre-authenticated MCP, it is classified into the correct tier, a lifecycle track is bootstrapped, and a status transition is applied via the provider's transition mechanism (not a raw status string).

**Acceptance Scenarios**:

1. **Given** a Jira ticket URL or issue key as the entry point, **When** the system parses it, **Then** it identifies the provider as Jira and extracts the entity identifier.
2. **Given** a recognized Jira entity, **When** it is fetched via the pre-authenticated MCP, **Then** its metadata is read without this feature performing any direct authentication, and it is classified into one of the four tiers.
3. **Given** a lifecycle status change for a Jira-tracked unit, **When** the status is applied, **Then** it is applied through the provider's workflow-transition mechanism, and a status change originating in the tracker is reconciled back into the lifecycle without creating a sync loop.
4. **Given** the same lifecycle definition, **When** a unit of work is tracked on GitHub, GitLab, Linear, or Jira, **Then** it flows through the identical phases with only the provider/entry point differing.

---

### User Story 5 - Govern and enforce the lifecycle over time (Priority: P3)

The lifecycle rules — the phase ordering, phase→command mapping, gating, hierarchy model, and provider mapping — are written into the project constitution as the versioned single source of truth, with dependent process documents kept consistent. The autonomous-development loop enforces the gates: it will not advance a unit of work (open a PR, merge) until all prior-phase gates, including the Verify smoke gate, pass; otherwise it halts and flags for a human. Drift — a skipped phase, missing smoke coverage, or a stale tracking state — is detectable.

**Why this priority**: Governance and automated enforcement make the lifecycle durable rather than aspirational, but they layer on top of US1–US4 and are not required to demonstrate initial value.

**Independent Test**: Amend the constitution with the lifecycle rules and confirm dependent docs/templates reflect them; then run the autonomous loop against a unit of work whose Verify gate fails and confirm the loop halts and flags for a human instead of advancing.

**Acceptance Scenarios**:

1. **Given** the lifecycle is codified in the constitution, **When** a phase-ordering or gate rule changes, **Then** it is changed in that one authoritative place and dependent process docs/templates stay consistent.
2. **Given** the autonomous loop processing a unit of work, **When** a prior-phase gate (e.g., the Verify smoke gate) has not passed, **Then** the loop does not advance the work (no PR/merge) and instead halts and flags for human attention.
3. **Given** a unit of work that skipped a phase or lacks required smoke coverage, **When** the work is audited, **Then** the drift is surfaced as a finding rather than passing unnoticed.

---

### Edge Cases

- **Phase-skip attempt**: A request for a later-phase action while in an earlier phase is refused with a state-violation that names the missing prerequisite — never silently honored.
- **Unrecognized entry point**: An entry string matching no known provider or an invalid issue key produces a clear error and creates no lifecycle state.
- **Missing/renamed tier**: A target tracker without a required tier (e.g., no "Initiative" type, or a Jira instance lacking Advanced-Roadmaps hierarchy) surfaces a configuration error with a documented fallback, not a silent mismap.
- **Partial hierarchy provisioning**: A parent is created but a child creation fails — the failed node is marked `FAILED_PROVISION` (remote id recorded), child creation halts, and the partial state is flagged for reconciliation; remote-side entities may persist (deletion is not guaranteed) but local state is never left orphaned.
- **Zero smoke coverage at Verify**: A shipped user-facing workflow with no smoke test fails the Verify gate (missing coverage is distinct from "all passed"); only a Sub-Task explicitly marked exempt (no user-facing surface) may complete without a test, and its exemption rationale is recorded.
- **Tracker-originated status change**: A human moves an item to "Done" directly in the tracker — the lifecycle reconciles the state without entering an infinite update loop.
- **Provider rate limiting**: Bulk top-down hierarchy creation is sequenced/queued so throttling does not corrupt the tree or drop nodes.
- **Concurrent units of work**: Multiple agents working different units do not corrupt each other's lifecycle state (state is isolated per unit, consistent with the per-application smoke catalog isolation).
- **Backward regression**: A defect found in Verify but rooted in Plan is handled as a logged regression to the earlier phase, not a forward-only patch.
- **Context/token drift mid-lifecycle**: A long-running session that loses adherence is re-anchored to the persisted phase so it resumes at the correct stage.
- **Sensitive values**: Tokens/credentials used for provider or verify operations never appear in logs, the state store, or reports in readable form.
- **Irreversible advancement under automation**: The autonomous loop never performs an irreversible advancement (merge) without all gates passing, consistent with the existing "agent opens PRs but does not merge unverified work" rule.

## Requirements *(mandatory)*

### Functional Requirements

#### Lifecycle definition & state gating

- **FR-001**: The system MUST define a single canonical, ordered development lifecycle of nine phases — (1) Specify, (2) Clarify, (3) Spec-Review (product), (4) Plan, (5) Task Creation, (6) Analyze, (7) Spec-Review (technical), (8) Implement, (9) Verify task-by-task — and MUST map each phase to one or more existing repository commands/skills executed in a defined order (not necessarily a single command per phase) rather than introducing a parallel mechanism.
- **FR-002**: Each phase MUST declare explicit entry criteria, exit criteria, the ordered command(s) that execute it (each with individual pass/fail semantics), and the artifact(s) it produces or updates. Where one command backs two phases (e.g., `/spec-review` for both the product pass and the technical pass), the phase MUST pass that command an explicit pass/mode identifier so its entry criteria, exit criteria, and verdict are interpreted distinctly per phase.
- **FR-003**: The system MUST track the current lifecycle phase ("state") for each unit of work, persisted so it survives across separate agent sessions and invocations.
- **FR-028**: A lifecycle track (a "unit of work") MUST be anchored at the Task tier (Tier 3): phases 1–7 (Specify through Spec-Review technical) execute once for the Task and record their artifacts at the appropriate ancestor tier per FR-015, while phases 8–9 (Implement, Verify task-by-task) iterate per child Sub-Task (Tier 4) as sub-states within the parent Task's track. The entity that holds `current_phase` is the Task-tier track; each Sub-Task carries its own Implement→Verify sub-state.
- **FR-004**: The system MUST enforce sequential progression — a phase MUST NOT begin until the prior phase's exit criteria are satisfied. For autonomous (agent-driven) work, a skip-forward attempt MUST be hard-refused with a state-violation error naming the missing prerequisite phase(s). For human-driven work, a skip MUST raise an advisory warning naming the missing prerequisite(s) and MUST be permitted only with a logged override reason.
- **FR-005**: The system MUST permit backward transitions (regressions) only when explicitly logged with a reason, re-entering the earlier phase rather than allowing a silent forward patch.
- **FR-006**: An actor operating the lifecycle MUST declare/anchor the active phase at the start of each unit of work, and the system MUST support re-anchoring mid-session (a periodic state reminder) to resist context/adherence drift.
- **FR-007**: The system MUST report, for any unit of work, its current phase, completed phases, and outstanding gates.
- **FR-027**: Review and analysis gates (Spec-Review product, Spec-Review technical, Analyze) MUST use the project constitution's verdict model to decide advancement: advance on `APPROVED` (Tier-1 checks pass AND Tier-2 score ≥0.60 / multi-agent consensus ≥80%), surface `NEEDS_REVIEW` as a warning, and halt on `BLOCKED` (any Tier-1 failure).

#### Verify gate ↔ smoke-test orchestrator

- **FR-008**: During the Implement phase, the implementer (agent or human) MUST author a tier-tagged smoke test for each user-facing workflow shipped, using the smoke-test orchestrator's existing append/upsert operation (idempotent per workflow identifier) — the lifecycle does NOT auto-generate test content. The Implement phase's exit criteria MUST validate that such a smoke test exists for every shipped user-facing workflow before advancing to Verify. A Sub-Task with no user-facing surface (e.g., internal refactor, infrastructure) MUST be explicitly marked exempt rather than left silently uncovered.
- **FR-009**: The Verify phase MUST execute the smoke suite filtered to at least the critical-path tier and MUST treat any non-zero verdict (failed, blocked, or empty/no-coverage) as a gate failure that prevents the unit of work from being marked complete.
- **FR-010**: The Verify gate MUST distinguish "no smoke coverage exists for the shipped workflow" from "all smoke tests passed," and MUST NOT report missing coverage as success.
- **FR-011**: The system MUST associate each verified user-facing Sub-Task with the smoke test(s) that exercise it (≥1 passing test per user-facing workflow), so verification is traceable task-by-task; an exempt Sub-Task MUST record its exemption rationale instead.
- **FR-012**: The Verify gate MUST consume the existing smoke-test orchestrator as-is (its append/run/list/prune operations, cumulative tiers, exit-code/verdict scheme, and machine-readable result output) without requiring changes to the orchestrator's runtime.

#### Four-tier hierarchy & provider abstraction

- **FR-013**: The system MUST represent work in a four-tier hierarchy — Initiative (Tier 1) → Epic (Tier 2) → Task (Tier 3) → Sub-Task (Tier 4) — independent of the backing provider.
- **FR-014**: The system MUST map each abstract tier to each supported provider's native construct, and MUST surface a configuration error (naming the unresolved tier) when a target instance lacks or renames a required tier, rather than mismapping silently.
- **FR-015**: The system MUST record lifecycle artifacts at the appropriate tier — high-level scope/specification at the Initiative/Epic, plan/analysis/technical design at the Task, implementation and per-task verification at the Sub-Task.
- **FR-016**: The system MUST consume the existing entry entity referenced by the entry point and provision only the missing descendant tiers (never recreating existing ancestors). When provisioning, it MUST create top-down — obtaining each parent's identifier before creating its children. On partial failure the system MUST NOT leave orphaned local state: it MUST mark the affected node `FAILED_PROVISION`, record any already-created remote entity's external identifier, halt creation of that node's children, and log the partial state for reconciliation. Transactional deletion of already-created remote entities is NOT promised (remote APIs may forbid it); the system MUST instead provide a reconciliation operation to resolve or adopt provider-side partials.
- **FR-017**: The system MUST keep its local hierarchy/state model decoupled from any single provider — using a generic representation (external identifier, provider type, tier level, parent reference, status) with no provider-specific storage assumptions.

#### Providers (GitHub, GitLab, Linear, Jira)

- **FR-018**: The system MUST support GitHub, GitLab, Linear, and Jira as issue-tracking providers under one provider-agnostic abstraction, reusing the repository's existing provider tooling and label/status registry.
- **FR-019**: The system MUST detect the provider and entity from an entry-point string (a ticket URL or an issue key), bootstrap the lifecycle state, and classify the entity into one of the four tiers; an unrecognized entry point MUST error without creating state.
- **FR-020**: The system MUST access Jira via the pre-authenticated MCP integration and MUST NOT implement bespoke authentication or credential storage for Jira in this feature.
- **FR-021**: The system MUST map lifecycle status changes to each provider's native state model — using Jira's workflow-transition mechanism (not free-text status strings) and the existing canonical labels for GitHub/GitLab/Linear — and MUST reconcile tracker-originated status changes without creating infinite sync loops.
- **FR-022**: All provider operations (entity creation, hierarchy linking, status transitions) MUST be idempotent so retries and re-runs do not duplicate entities or transitions.

#### Governance & enforcement

- **FR-023**: The lifecycle definition, phase→command mapping, gating rules, hierarchy model, and provider mapping MUST be codified in the project constitution as the authoritative, versioned source of truth, with dependent process documents/templates kept in sync.
- **FR-024**: The autonomous-development loop MUST enforce the lifecycle — it MUST NOT merge or mark a unit of work complete until the gating criteria of all prior phases, including the Verify smoke gate, are satisfied; otherwise it MUST halt and flag the unit for human attention. Opening a (draft) PR is a permitted Verify-phase action that triggers CI-backed verification — it is the mechanism for *entering* Verify, not an advancement *past* it.
- **FR-025**: The system MUST keep sensitive values (tokens, credentials) out of logs, the state store, and reports in readable form, sourcing them at run time from the environment/MCP, consistent with the smoke framework's handling.
- **FR-026**: The system MUST make lifecycle drift detectable — a skipped phase, missing required smoke coverage, or a stale tracking state MUST be surfaceable as an audit finding rather than passing unnoticed.

### Key Entities *(include if feature involves data)*

- **Lifecycle Definition**: The canonical ordered set of nine phases; for each phase: its name/order, entry and exit criteria, the mapped executing command/skill, the artifact(s) it produces, and its gate criteria. The governed source of truth.
- **Phase**: One stage of the lifecycle, with a state value, a mapped command, and pass/fail gate criteria; the unit of sequencing and gating.
- **Lifecycle Track (Work Item)**: A unit of work flowing through the lifecycle — current phase, completed phases, a regression/transition log, and a link to its tracker entity and tier.
- **Issue Hierarchy Node**: An abstract tracked entity at one of the four tiers, holding an external identifier, provider type, tier level, parent reference, and status — provider-independent.
- **Provider Mapping**: The translation between abstract tiers/statuses and a specific provider's native types and transitions (e.g., Jira transition IDs, GitHub Sub-Issues, canonical labels).
- **Smoke Coverage Link**: The association between a Sub-Task (or Task) and the smoke test(s) that verify it, enabling task-by-task verification traceability.
- **Gate Result**: The outcome of a phase's exit criteria — in particular the Verify gate's verdict and exit signal (pass / fail / blocked / empty-no-coverage).
- **Entry Point**: The ticket URL or issue key that bootstraps a Lifecycle Track and determines the provider and starting tier.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given an entry-point issue key/URL, an actor can drive a unit of work through all nine phases with the active phase visible at every step, and 100% of phase-skip attempts are refused with the missing prerequisite named.
- **SC-002**: 100% of autonomous (agent-driven) attempts to perform a later-phase action while in an earlier phase are blocked; human attempts raise an advisory warning and proceed only with a logged override.
- **SC-003**: 0% of units of work reach "done" with a non-exempt user-facing workflow lacking a passing critical-path smoke test — every non-exempt user-facing workflow has ≥1 passing smoke test, and every exempt Sub-Task carries a recorded rationale.
- **SC-004**: The same lifecycle definition tracks a unit of work end-to-end on all four supported providers (GitHub, GitLab, Linear, Jira) with no change other than the provider/entry point.
- **SC-005**: The four-tier hierarchy can be represented and navigated parent↔child on every supported provider, and 100% of missing/renamed-tier cases produce a configuration error (never a silent mismap).
- **SC-006**: 100% of partial hierarchy-provisioning failures leave zero orphaned local state — the failed node is marked `FAILED_PROVISION` and flagged for reconciliation — never a silently corrupt tree.
- **SC-007**: For any unit of work, a contributor can obtain its current phase, completed phases, and outstanding gates ("where is this and what's blocking it") in a single inspection.
- **SC-008**: A change to phase ordering or a gate rule is made in exactly one authoritative location (the constitution) and dependent process docs/templates remain consistent with it.
- **SC-009**: No sensitive value appears in any lifecycle log, state store, or report across the full workflow.
- **SC-010**: A status change made directly in a tracker is reconciled into the lifecycle within one autonomous-loop iteration without producing a sync loop.
- **SC-011**: When the Verify gate fails under automation, the autonomous loop halts and flags for a human in 100% of cases — it never advances (PR/merge) past a failing gate.

## Assumptions

- **Formalizes existing commands**: This feature wires and governs existing repository commands/skills rather than reimplementing them. The phase→command map is: Specify = `/speckit-specify`; Clarify = `/speckit-clarify`; Spec-Review (product) = `/spec-review` (product-pass mode); Plan = `/speckit-plan`; Task Creation = `/speckit-tasks` (+ `/speckit-taskstoissues` to provision the tracker hierarchy); Analyze = `/speckit-analyze`; Spec-Review (technical) = `/spec-review` (technical-pass mode, see FR-002); Implement = `/speckit-implement`; Verify task-by-task = `/speckit-implement-review` + the smoke-test orchestrator run (with `/verify` and `/pr-regression-smoke` available as broader gates).
- **Verify backbone already exists**: The Verify gate consumes the already-implemented smoke-test orchestrator (spec `363-smoke-test-orchestrator`) — its `append`/`run`/`list`/`prune` operations, cumulative `Lite ⊆ Full ⊆ Full+Extra` tiers, `0/1/2` exit-code scheme, and machine-readable result output. No changes to the orchestrator's runtime are assumed.
- **Codification target**: The project constitution at `.specify/memory/constitution.md` (currently v1.0.0) is amended to add the lifecycle as a governing section/principle; the amendment is a MINOR-or-greater version bump with dependent templates kept in sync via `/speckit-constitution`.
- **Enforcement host**: The autonomous-development loop (`/auto-issue-dev`, extended by the draft `361-auto-dev-merge-loop`) is where gate enforcement lives; the existing rule that the loop opens PRs but does not merge unverified work is preserved and extended to the full gate set.
- **Jira via pre-auth MCP**: Jira is reached through the pre-authenticated Atlassian MCP already registered in the repository's MCP registry; "pre-authenticated" means no bespoke OAuth/token flow is built in this feature. Whether Jira operations are wrapped behind the MCP directly or behind a thin `jira_ops`-style adapter (mirroring `linear_ops`) is a planning-phase decision.
- **Provider abstraction reuse**: Existing tooling is reused — GitHub/GitLab via `git_ops.sh`/`git_platform.sh`, Linear via `linear_ops.sh` (which already supports parent/child sub-issues), and the canonical label registry (`labels.yml` + `label_sync.sh`). GitHub Tier-4 uses native Sub-Issues (not markdown checklists); Jira targets Jira Cloud semantics with hierarchy via parent fields.
- **Gating strictness**: Hard refusal (halt) applies to autonomous/agent-driven work; human-driven work receives an advisory warning that permits a logged override. A fully unenforced mode is out of scope.
- **Hierarchy is consume-and-extend**: The system reads the existing entry entity and provisions only missing descendant tiers; it does not recreate ancestors that already exist in the tracker.
- **Smoke coverage is per user-facing workflow**: Each shipped user-facing workflow needs ≥1 passing critical-path smoke test; non-user-facing Sub-Tasks (refactors, infra) are explicitly exempt with a recorded rationale. Review/analysis gates reuse the constitution's `APPROVED`/`NEEDS_REVIEW`/`BLOCKED` verdict model.
- **Status reconciliation is loop-based**: Tracker-originated status changes are reconciled during autonomous-loop iterations (poll-based). A real-time bidirectional webhook receiver is out of scope and may be a later feature.
- **Out of scope for this feature**: Building the smoke-test runtime (already delivered in 363); bespoke authentication flows (covered by pre-auth MCP); a real-time webhook sync server; load/performance and visual-regression testing; and provider-specific advanced-hierarchy features beyond best-effort tier mapping.

## Dependencies

- **Spec `363-smoke-test-orchestrator`** (implemented) — the Verify-phase backbone (catalog, tiers, runner, exit codes, JUnit output).
- **Speckit command suite** — `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-taskstoissues`, `/speckit-analyze`, `/speckit-implement`, `/speckit-implement-review`, `/speckit-constitution`, and the `/spec-review` skill — the executors for the nine phases.
- **Autonomous-development loop** — `/auto-issue-dev` and the draft `361-auto-dev-merge-loop` state machine — the enforcement host.
- **Provider tooling** — `git_ops.sh`, `git_platform.sh`, `linear_ops.sh`, `labels.yml`, `label_sync.sh` — the provider-abstraction and label/status surface that Jira plugs into.
- **Pre-authenticated Atlassian (Jira) MCP** — registered in the repository's MCP registry — the Jira access layer.
- **Project constitution** (`.specify/memory/constitution.md`) and dependent `.specify/templates/*` — the governance surface the lifecycle is codified into.
