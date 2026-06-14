# Feature Specification: Autonomous Issue Implementation Orchestrator

**Feature Branch**: `004-autonomous-issue-orchestrator`

**Created**: 2026-06-14

**Status**: Draft

**Input**: User description: "AI Core of an Autonomous Issue Implementation Orchestrator — a stateless decision/synthesis engine, invoked once per phase transition by a polling orchestration daemon, that drives GitHub/GitLab issues from specification to a clean Pull Request across six phases (ingestion & prioritization, dual-model clarification synthesis, planning & tasking, pre-implementation analysis gate, post-implementation verification gate, code review & PR resolution), integrating `gh`/`glab`, `speckit`, and the `agy` CLI, under a strict machine-parseable JSON output contract."

## Clarifications

### Session 2026-06-14

- Q: Concurrency — single vs. multiple active issues per pipeline run? → A: Single active issue per run; the daemon processes one issue end-to-end before starting the next (concurrency deferred to a later version).
- Q: Autonomy boundary — does any internal phase require human sign-off? → A: Fully autonomous through PR-open; no human gate at the spec, plan, or implementation phases. The opened PR is the sole human review checkpoint.
- Q: Escalation bound — when does the orchestrator stop retrying a failing phase? → A: Fixed cap of 2 attempts per phase; on the 2nd consecutive failure of the same phase the orchestrator escalates (`needs_escalation`). The daemon supplies the attempt count so the stateless engine can enforce the cap.
- Q: Tool-failure semantics — is a tool that fails to run treated like analysis findings? → A: No. A failed/unavailable *required* tool (e.g., `gh`/`glab`/`speckit`) is treated as missing input → status `blocked` + escalation, distinct from a tool that ran and returned findings (→ gate-block with fix directives). The advisory `agy` tool is exempt: its absence does not block (synthesis proceeds on the engine's own reasoning).
- Q: Observability — must orchestrator decisions be durably recorded? → A: Yes. The daemon persists a durable, append-only audit record of every response (phase, status, reasoning trace, escalations) for later review.
- Q: Should there be a post-implementation verification gate before the PR opens? → A: Yes. A new phase runs after `speckit implement` and before PR-open, verifying design intent (per-task acceptance criteria), functionality (tests pass), and development standards. It reuses the repo's tiered model (`validation_criteria.yml`): Tier 1 findings (security, error handling, breaking changes, acceptance-criteria coverage, cross-verification) BLOCK PR-open; Tier 2 findings (bugs, performance, maintainability, test coverage) are advisory and annotated on the PR. This makes the pipeline six phases; "Code review & PR resolution" becomes Phase 6.

### Session 2026-06-14 (round 2)

- Q: Are the orchestrator's own phase decisions cross-verified by multiple agents, and where? → A: Gate-targeted consensus. Multi-agent cross-verification runs at the two gates (pre-implementation analysis, post-implementation verification) applying the repo's consensus thresholds (≥80% auto-proceed, 50–79% proceed with disagreements highlighted, <50% escalate to human). Phase 2 retains the `agy` second opinion; other phases are single-pass.
- Q: What happens when the cross-verification agents run out of tokens/credit? → A: Pause and resume — the engine signals a transient resource-unavailable condition (not a failure), and the daemon pauses and re-invokes the phase when agents become available or on a periodic check (default hourly). This MUST NOT count toward the per-phase 2-attempt cap (FR-027) and MUST NOT trigger human escalation; no work is lost or discarded during the pause.
- Q: How is issue severity determined for prioritization? → A: Metadata-first — explicit severity/priority labels or fields are authoritative; severity is inferred from the issue body only when no such metadata exists, and the source used is recorded in the reasoning trace.
- Q: Should there be a human kill-switch label that blocks automation? → A: Yes. A designated automation-block label (canonical name `no-automation`, registered in `labels.yml`) prevents the orchestrator from selecting, advancing, or implementing any issue while the label is active. The label is re-checked before each phase advance, so applying it mid-pipeline halts that issue before implementation or PR-open.
- Q: How are secrets/PII handled in the durable audit log? → A: Redact. Known secret/credential/PII patterns MUST be masked in all persisted outputs and reasoning traces, and raw tokens/keys MUST never be emitted, before content is durably recorded (FR-029).
- Q: Is there a performance/throughput target? → A: Yes. Median small-scope issue progresses from selection to an opened PR within 30 minutes of active processing, measured excluding human-review waits and resource-pause (token/credit) waits.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prioritized issue selection (Priority: P1)

An engineering team has a backlog of open issues. They want the orchestrator to decide *which issue to work next* — accounting not just for raw severity but for which issues unblock others — and to explain that choice in an auditable way.

**Why this priority**: Selecting the right next unit of work is the entry point of the entire pipeline; every downstream phase depends on a defensible choice. On its own, this slice is a usable triage-recommendation engine that delivers value even if no later phase is built.

**Independent Test**: Provide a set of raw issue records (including some with stated dependencies on others) and confirm the orchestrator returns a complete priority ranking, a single top choice with written justification, and explicit dependency notes — with an unblocking issue correctly out-ranking an isolated higher-severity one.

**Acceptance Scenarios**:

1. **Given** a backlog where issue B is lower-severity but blocks three other issues and issue A is higher-severity but isolated, **When** the orchestrator runs prioritization, **Then** B is ranked above A and the justification explicitly states the unblock-vs-severity trade-off.
2. **Given** a backlog with no inter-issue dependencies, **When** prioritization runs, **Then** issues are ranked by severity and the dependency notes list is empty.
3. **Given** identical issue input submitted twice, **When** prioritization runs each time, **Then** the ranked order and justification are identical.

---

### User Story 2 - Doubly-gated implementation pipeline (Priority: P1)

Once an issue is selected and specified, the team wants the orchestrator to produce a dependency-ordered, independently verifiable task breakdown, to **refuse to start implementation** unless the pre-implementation analysis is completely clean, and — after code is generated — to **refuse to open a PR** unless a post-implementation verification gate confirms the implementation meets design intent, functionality, and development standards.

**Why this priority**: The two gates are the system's core safety property — the pre-implementation gate prevents generating code on a broken baseline, and the post-implementation gate guarantees that a PR is only ever opened once it has been self-verified. Together with planning, this is the slice that makes "autonomous to a *clean* PR" actually mean clean, rather than merely opened.

**Independent Test**: Feed the orchestrator (a) an approved specification and confirm it returns a strictly ordered task list where every task names its acceptance condition and review criteria; (b) feed pre-implementation analysis with one warning and confirm implementation is blocked with a required-fix directive, and clean analysis and confirm implementation is approved; then (c) feed post-implementation results where one task's acceptance criterion is unmet (a Tier 1 finding) and confirm PR-open is blocked, and results that are Tier-1-clean and confirm PR-open is approved.

**Acceptance Scenarios**:

1. **Given** an approved specification, **When** task generation runs, **Then** every task has a sequence number, an acceptance condition, the review criteria it addresses, and an explicit dependency list.
2. **Given** pre-implementation analysis results containing any finding (error, warning, or regression), **When** the analysis gate evaluates them, **Then** the gate is "blocked", implementation is not approved, and each finding has a corresponding fix directive.
3. **Given** pre-implementation analysis results with zero findings, **When** the analysis gate evaluates them, **Then** the gate is "clean", the required-fixes list is empty, and implementation is approved.
4. **Given** post-implementation results where a task's acceptance criterion is unmet, a test fails, or a Tier 1 standard is violated, **When** the verification gate evaluates them, **Then** the verdict is "blocked", PR-open is not approved, and each blocking finding has a remediation directive.
5. **Given** post-implementation results with no Tier 1 findings (Tier 2 advisory findings may remain), **When** the verification gate evaluates them, **Then** the verdict is "verified", PR-open is approved, and any Tier 2 findings are emitted as advisory annotations rather than blockers.

---

### User Story 3 - Arbitrated clarification synthesis (Priority: P2)

The team uses a second AI assistant (`agy`) for a parallel opinion. They want the orchestrator to act as the final arbitrator between its own reasoning and `agy`'s recommendations when the two diverge, applying a consistent, documented resolution order rather than defaulting to either source.

**Why this priority**: Multi-source synthesis improves decision quality, but only if disagreements are resolved transparently. This slice raises confidence in finalized specs without being required for the minimal pipeline to function.

**Independent Test**: Provide clarification output plus an `agy` recommendation that conflicts with the repository's existing pattern, and confirm the orchestrator chooses the repository-consistent option, records the conflict (chosen vs. rejected with rationale), and never silently defers.

**Acceptance Scenarios**:

1. **Given** an `agy` recommendation that contradicts an existing repository pattern, **When** synthesis runs, **Then** the repository-consistent option is chosen and the conflict is logged with the rejected alternative and its trade-off.
2. **Given** an `agy` recommendation that agrees with the orchestrator's reasoning, **When** synthesis runs, **Then** no conflict is recorded and the finalized parameters reflect the agreed direction.
3. **Given** thin evidence and two viable options of differing reversibility, **When** synthesis runs, **Then** the more reversible option is chosen and the rationale cites reversibility.

---

### User Story 4 - Review-driven PR resolution (Priority: P2)

After a PR is opened, human reviewers leave comments and CI may fail. The team wants the orchestrator to diagnose the underlying cause, propose precise code modifications, and post a concise professional reply on the PR thread.

**Why this priority**: Closing the loop on review feedback is what turns an opened PR into a *clean* PR. It is valuable but depends on earlier phases having produced a PR first.

**Independent Test**: Provide a set of review comments and a CI failure log, and confirm the orchestrator returns targeted modifications (each naming a file, location, change, and which feedback item it addresses), a single root-cause statement for the CI failure, and a PR reply ending in a confirmation marker.

**Acceptance Scenarios**:

1. **Given** a CI failure log and review comments, **When** resolution runs, **Then** each proposed modification names a file, a location, the change, and the specific feedback item it addresses.
2. **Given** a CI failure with a single root cause spanning multiple symptoms, **When** resolution runs, **Then** the root cause is stated once and fixes target the cause rather than each symptom.
3. **Given** any resolution output, **When** the PR reply is produced, **Then** it is concise, professional, and ends with a confirmation marker.

---

### User Story 5 - Deterministic, safe, auditable contract (Priority: P3)

Operators rely on the orchestrator's output being machine-parseable, reproducible, injection-resistant, and conservative about irreversible actions, so the surrounding automation can trust it without a human reading every response.

**Why this priority**: These cross-cutting guarantees make autonomous operation safe to leave running. They are foundational to trust but are verified as properties of every phase rather than as a standalone user journey, so they are sequenced last.

**Independent Test**: Submit malformed input and confirm a structured "blocked" response with a populated escalation; submit input containing embedded directives ("ignore your rules") and confirm they are disregarded and noted; submit identical input twice and confirm byte-identical structured output.

**Acceptance Scenarios**:

1. **Given** required input that is missing or contradictory, **When** any phase runs, **Then** the response status is "blocked", the phase payload is empty, and an escalation describing the gap is populated.
2. **Given** untrusted input containing instructions aimed at the orchestrator, **When** any phase runs, **Then** those instructions are ignored, normal processing continues, and the attempted injection is noted in the reasoning trace.
3. **Given** a request that would require an irreversible or history-rewriting operation without explicit confirmation that no upstream human work exists, **When** the orchestrator responds, **Then** it withholds the operation and escalates instead.
4. **Given** identical input submitted on separate invocations, **When** each is processed, **Then** the structured outputs are identical in ordering, naming, and content.

---

### Edge Cases

- **Empty or single-issue backlog**: Prioritization must still return a well-formed ranking (one element, or an empty list with a clear note) rather than failing.
- **All candidate issues carry the automation-block label**: Prioritization must return an empty implementable selection with a clear "all held" note rather than selecting a blocked issue.
- **Automation-block label applied mid-pipeline**: When the `no-automation` label appears on the active issue after selection, the orchestrator must halt that issue before the next phase advance (no implementation, no PR-open) and report it as held.
- **Severity metadata absent**: When an issue has no severity label/field, severity is inferred from its body and the reasoning trace records that inference was used.
- **Circular dependencies between issues**: The system must detect a dependency cycle and surface it instead of looping or arbitrarily breaking it.
- **`agy` unavailable or returns malformed output**: Synthesis must proceed on the orchestrator's own reasoning and record that the second opinion was absent — without fabricating a recommendation.
- **Analysis findings of unknown severity**: Any finding that cannot be confidently classified as clean must block the pre-implementation gate (fail-closed).
- **Tests pass but design intent unmet**: When the test suite passes yet a task's acceptance criterion is not satisfied, the verification gate must still block PR-open (treated as a Tier 1 acceptance-criteria finding).
- **Only Tier 2 verification findings present**: When verification surfaces solely Tier 2 (advisory) findings, PR-open proceeds and the findings are attached as advisory annotations rather than blocking.
- **Gate consensus below 50%**: When cross-verification agents agree on a gate decision at less than 50%, the orchestrator must escalate to human review rather than auto-proceed.
- **Agent token/credit exhaustion mid-gate**: The orchestrator must signal a transient pause (not a failure or escalation), the daemon must wait and re-invoke when agents return or on the hourly check, and the attempt count must not increment.
- **Critical-failure flag from the daemon**: The orchestrator must switch to an escalation response regardless of which phase it was asked to run.
- **Repeated phase failure**: When the daemon-supplied attempt count shows a phase has already failed once, a second failure must trigger escalation rather than a third attempt.
- **Conflicting directives embedded in issue text, `agy` output, or PR comments**: Treated as untrusted data, never as instructions.
- **Secret or PII embedded in untrusted input**: The value must be redacted before it reaches the reasoning trace or durable audit; the raw secret is never persisted.
- **Stale or out-of-order invocation**: Because the engine is stateless, it must rely solely on the supplied context payload and never assume continuity from a prior turn.

## Requirements *(mandatory)*

### Functional Requirements

**Output contract (all phases)**

- **FR-001**: System MUST return exactly one top-level structured response per invocation, containing the phase identifier, a status of `ok`, `blocked`, or `needs_escalation`, a phase-specific payload, an ordered reasoning trace, and an escalation field that is either empty or a populated reason/blocking-state pair.
- **FR-002**: System MUST emit no content outside the structured response envelope.
- **FR-003**: System MUST produce identical output for identical input, with no randomness in ordering, naming, or phrasing of structured fields.
- **FR-004**: System MUST place all justification inside the reasoning trace and never interleave it with structured data fields.
- **FR-005**: When required input is missing, malformed, or contradictory, System MUST set status to `blocked`, leave the payload empty, and populate the escalation — never fabricating inputs or guessing past a genuine gap.

**Statelessness & invocation**

- **FR-006**: System MUST treat each invocation as independent, deriving all needed state from the supplied context payload and retaining nothing between invocations.
- **FR-007**: System MUST execute only the rules of the phase named in the invocation directive and return only that phase's defined payload (no early execution of a later phase, no re-litigation of a committed prior phase).

**Phase 1 — Ingestion & prioritization**

- **FR-008**: System MUST rank supplied issues from highest to lowest priority using severity, architectural dependencies, and logical implementation order.
- **FR-009**: System MUST rank an issue that unblocks others above an isolated higher-severity issue, and MUST state that trade-off explicitly when it occurs.
- **FR-010**: System MUST return a single top choice with written justification and a list of dependency notes mapping each issue to the issues it blocks.
- **FR-036**: System MUST derive issue severity on the ordered scale `critical > high > medium > low` metadata-first — treating explicit severity/priority labels or fields as authoritative and inferring severity from the issue body only when no such metadata exists — and MUST record which source was used in the reasoning trace.

**Phase 2 — Dual-model clarification synthesis**

- **FR-011**: System MUST act as the final arbitrator between its own reasoning and `agy` recommendations, applying this resolution order when they diverge: (1) consistency with existing repository patterns, (2) modularity/type-safety/security, (3) reversible over irreversible decisions under thin evidence.
- **FR-012**: System MUST, for each material conflict with `agy`, record the topic, the chosen option, the rejected alternative, and the rationale — neither deferring to `agy` by default nor overriding it without a logged reason.
- **FR-013**: System MUST output finalized specification parameters suitable to feed back into the specification toolchain, plus any remaining open questions (empty when none remain).

**Phase 3 — Planning & tasking**

- **FR-014**: System MUST produce a strict, linear, dependency-ordered task breakdown from the approved specification.
- **FR-015**: System MUST make every task independently verifiable, naming its acceptance condition and declaring its task dependencies.
- **FR-016**: System MUST integrate review criteria into each task rather than appending review as a trailing step, recording which criteria each task addresses.

**Phase 4 — Analysis & implementation gate**

- **FR-017**: System MUST block implementation when analysis surfaces any finding of any severity (error, warning, or regression), emitting a required-fix directive per finding.
- **FR-018**: System MUST approve implementation only when analysis is completely clean, in which case the required-fixes list is empty.
- **FR-019**: System MUST fail closed — any finding that cannot be confidently classified as clean blocks the gate.
- **FR-028**: System MUST distinguish a *required* tool that failed to produce usable output (unavailable, crashed, or unparseable) from a tool that ran and returned findings: the former is treated as missing input per FR-005 (status `blocked`, empty payload, populated escalation), while the latter drives the normal gate-block-with-fix-directives path. The advisory `agy` tool is exempt — its absence does not block synthesis.

**Phase 5 — Post-implementation verification gate**

- **FR-030**: After implementation and before any PR is opened, System MUST evaluate the implementation against three dimensions and emit a verdict (`verified` or `blocked`) with a remediation directive per blocking finding: (a) **design intent** — every Phase 3 task's acceptance criteria are satisfied; (b) **functionality** — the test suite passes and behavior matches the functional requirements; (c) **development standards** — code-quality, type-safety, and security checks.
- **FR-031**: System MUST classify verification findings using the repository's tiered validation model: **Tier 1** (security, error handling, breaking changes, acceptance-criteria coverage, cross-verification) findings MUST block PR-open (`blocked`, PR-open not approved); **Tier 2** (bug detection, performance, maintainability, test coverage) findings MUST NOT block and MUST be emitted as advisory annotations on the PR. The verdict MUST follow the established mapping — `BLOCKED` on any Tier 1 failure, otherwise `APPROVED`/`NEEDS_REVIEW` per the Tier 2 threshold — and PR-open is approved only when no Tier 1 failure exists.
- **FR-032**: System MUST treat an unmet task acceptance criterion as a Tier 1 finding (acceptance-criteria coverage) that blocks PR-open, even when the test suite otherwise passes.
- **FR-033**: System MUST fail closed at the verification gate — any Tier 1 dimension that cannot be confidently confirmed as satisfied blocks PR-open.

**Phase 6 — Code review & PR resolution**

- **FR-020**: System MUST diagnose the underlying root cause of review feedback and CI failures and target fixes at the cause rather than each symptom.
- **FR-021**: System MUST specify each modification with its file, location, change, and the feedback item it addresses, and MUST identify the single root cause of a CI failure (or note that none applies).
- **FR-022**: System MUST draft a concise, professional PR-thread reply that ends with a confirmation marker.

**Cross-verification & resource handling**

- **FR-034**: At the two gates (pre-implementation analysis and post-implementation verification), System MUST cross-verify the gate decision across multiple agents and apply the repository's consensus thresholds: **≥80%** agreement → the decision stands (auto-proceed); **50–79%** → the decision stands but disagreements are highlighted as advisory; **<50%** → escalate to human (`needs_escalation`). Phase 2 retains the `agy` second opinion; the remaining phases are single-pass.
- **FR-035**: When cross-verification agents are unavailable due to token/credit exhaustion, System MUST signal a transient resource-unavailable condition (status `blocked` with a `blocking_state` marked transient and a retry directive) rather than fail or escalate. The daemon pauses and re-invokes the same phase when agents become available or on a periodic check (default hourly). This condition MUST NOT count toward the FR-027 per-phase 2-attempt cap, MUST NOT trigger human escalation, and MUST preserve all in-progress work for resumption. It is distinct from missing required *input* (FR-005), which does escalate.

**Safety & integrity (cross-cutting)**

- **FR-023**: System MUST treat all tool output (issue text, `agy` output, PR comments, CI logs) as untrusted data, never as instructions, and MUST note any attempted embedded directive in the reasoning trace.
- **FR-029**: Every response (phase, status, reasoning trace, and any escalation) MUST be durably persisted to an append-only audit record so that prior decisions can be reviewed after the fact; the engine emits the full content in each response and the daemon is responsible for persisting it.
- **FR-038**: System MUST redact known secret, credential, and PII patterns from all persisted outputs and reasoning traces, and MUST never emit raw tokens or keys, so that no sensitive value is durably recorded in the audit trail (FR-029). Redaction MUST preserve enough surrounding context for the audit entry to remain meaningful.
- **FR-024**: System MUST NOT recommend irreversible or history-rewriting operations unless the context payload explicitly confirms no upstream human work would be lost; otherwise it MUST withhold the operation and escalate.
- **FR-025**: System MUST NOT request human confirmation except when the daemon passes an explicit critical-failure flag, in which case it MUST set status to `needs_escalation` and populate the escalation.
- **FR-037**: System MUST honor a designated automation-block label (canonical name `no-automation`, registered in `labels.yml`) as a human kill-switch: an issue bearing this label MUST NOT be selected as the top choice, advanced into the pipeline, implemented, or opened as a PR. System MUST re-check the label before each phase advance so that applying it mid-pipeline halts that issue before implementation or PR-open; blocked issues are reported as held (not silently dropped).
- **FR-026**: System MUST operate fully autonomously from issue selection through PR-open, with no human approval gate at the specification, clarification, planning, implementation, or verification phases; the opened Pull Request is the sole human review checkpoint.
- **FR-027**: System MUST enforce a maximum of 2 attempts per phase using a per-phase attempt count supplied in the context payload; on the 2nd consecutive failure of the same phase it MUST set status to `needs_escalation` and populate the escalation rather than retry further.

### Key Entities *(include if feature involves data)*

- **Issue**: A unit of work drawn from the issue tracker, with an identifier, descriptive text, optional declared dependencies, labels (including the optional `no-automation` block label), and severity derived metadata-first (from a severity/priority label or field, or inferred from the body when absent).
- **Context Payload**: The complete per-invocation input, carrying the current-phase directive and all state the engine needs (it holds no state of its own).
- **Response Envelope**: The single structured object every invocation returns — phase, status, payload, reasoning trace, and escalation.
- **Phase**: One of the six defined stages of the pipeline, each with its own required payload shape and rules.
- **Specification**: The approved description of the selected issue's intended change, produced and refined across phases 1–2.
- **Task**: An independently verifiable unit of the implementation plan, with a sequence position, acceptance condition, addressed review criteria, and dependencies.
- **Analysis Finding**: A reported issue from the pre-implementation analysis, with a severity and optional file location, that drives the pre-implementation gate decision.
- **Verification Result**: The outcome of the post-implementation gate — a verdict (`verified`/`blocked`), the per-dimension findings (design intent, functionality, development standards) each classified Tier 1 or Tier 2, and remediation directives for blocking findings — that drives the PR-open decision.
- **Recommendation (agy)**: A second-opinion input considered during clarification synthesis, treated as advisory data subject to arbitration.
- **PR Feedback Item**: A human review comment or CI failure to be resolved, mapped to one or more proposed modifications.
- **Consensus Result**: The outcome of multi-agent cross-verification at a gate — the agreement level (mapped to ≥80% / 50–79% / <50% bands), the per-agent votes, and any highlighted disagreements — that determines whether the gate auto-proceeds, proceeds-with-flags, or escalates.
- **Escalation**: A structured signal that processing cannot safely continue, carrying a reason and a description of the blocking state. A *transient* blocking state (e.g., agent token/credit exhaustion) signals a pause-and-retry rather than a human escalation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of orchestrator responses conform to the defined response envelope and parse successfully on the first attempt, with zero responses containing content outside the envelope.
- **SC-002**: Identical input produces identical output on 100% of repeated invocations (full determinism).
- **SC-003**: Across a representative backlog, human operators agree with the orchestrator's top issue choice at least 90% of the time.
- **SC-004**: Implementation is approved in 0% of cases where any analysis finding is present (the gate never leaks a dirty state).
- **SC-005**: 100% of malformed, missing, or contradictory inputs result in a `blocked` status with a populated escalation rather than a fabricated or partial result.
- **SC-006**: 100% of embedded directives placed in untrusted inputs are ignored and recorded, with zero instances of the orchestrator acting on them.
- **SC-007**: At least 80% of small-scope issues progress from selection to an opened PR without human intervention beyond the final review.
- **SC-008**: At least 75% of review/CI feedback items are resolved at root cause within two resolution cycles, with no recurrence of the same root cause in the same PR.
- **SC-009**: Irreversible or history-rewriting operations are recommended in 0% of cases lacking explicit confirmation that no upstream human work would be lost.
- **SC-010**: 100% of orchestrator responses are captured in the durable append-only audit record, so any opened PR can be traced back to the full decision history that produced it.
- **SC-011**: 0% of PRs are opened while any Tier 1 verification finding (unmet acceptance criterion, failing test, or violated Tier 1 standard) is unresolved — the verification gate never leaks a non-verified implementation.
- **SC-012**: At least 90% of PRs opened by the orchestrator pass CI on the first run, demonstrating that the verification gate catches defects before PR-open rather than deferring them to CI and the human reviewer.
- **SC-013**: 100% of gate decisions with below-50% cross-verification consensus are escalated to a human rather than auto-proceeding.
- **SC-014**: When cross-verification agents are token/credit-exhausted, 0% of phases are counted as failed attempts and 0% of in-progress work is discarded — the paused phase resumes and completes once agent capacity returns.
- **SC-015**: 0% of issues bearing the `no-automation` label are ever selected, implemented, or advanced to a PR, including when the label is applied after selection but before PR-open.
- **SC-016**: 0% of persisted audit records contain unredacted secrets, credentials, or PII when tested against a corpus of known secret/PII patterns embedded in untrusted inputs.
- **SC-017**: The median small-scope issue progresses from selection to an opened PR within 30 minutes of active processing time, measured excluding human-review waits and resource-pause (token/credit) waits.

## Assumptions

- **Scope boundary — PR, not merge**: The orchestrator drives work to a *clean, review-ready Pull Request*; opening or merging is the endpoint, and final merge remains a human action. Auto-merge is out of scope for this feature.
- **Single active issue per pipeline run**: Each end-to-end pipeline run advances one selected issue; concurrent multi-issue pipelines are out of scope for the initial version.
- **Daemon owns execution and time**: A separate long-running orchestration daemon performs all command execution, Git operations, polling, and timeouts, and invokes the decision engine once per phase transition. The engine never runs commands or controls time.
- **Tooling availability**: `gh` or `glab`, `speckit` (with `specify`, `clarify`, `plan`, `tasks`, `analysis`, `implement`), and the `agy` CLI are installed and their outputs are supplied to the engine as parsed data.
- **Existing repository conventions are authoritative**: When resolving conflicts, the current repository's established patterns take precedence, consistent with the orchestration guidance already in this project.
- **Reviewers and CI provide structured feedback**: Human review comments and CI results are collected by the daemon's polling window and passed to the engine; the engine does not poll for them itself.
- **"Clean analysis" means zero findings**: The pre-implementation gate is fail-closed; there is no configurable tolerance threshold for findings in the initial version.
- **Active processing time excludes external waits**: The SC-017 performance target measures only time the system is actively working an issue; time spent awaiting human review or paused on agent token/credit exhaustion is excluded. A "small-scope issue" is one whose implementation touches a bounded, single-component change.
- **Multiple cross-verification agents are available**: The two gates assume access to more than one agent/model for consensus; when that capacity is exhausted the pause-and-resume behavior (FR-035) applies.
- **Label registry extension**: The `no-automation` block label is added to the canonical label registry (`labels.yml`) and synced across platforms via the existing label-sync mechanism.
