# Feature Specification: Critic-Driven Development Loop (CDDL)

**Feature Branch**: `482-critic-dev-loop`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "Critic-Driven Development Loop (CDDL) — integrate a two-phase, critic-gated implementation loop into Manifest. An input-agnostic adapter accepts either a Speckit feature directory or a Superpowers design-doc pair and normalizes it into a spec+plan context. Phase 1 (clarification gate): a QA/security critic and an architecture critic independently interrogate the artifacts for holes; the operator answers; implementation may not begin until both critics explicitly declare clarification complete. Phase 2 (implementation loop): a dedicated implementer role produces the change, both critics independently audit it, deficiencies feed back into the next iteration, and the loop exits only on dual explicit approval or a bounded iteration ceiling. Roles are defined as editable configurations; the loop is exposed as a single user-facing skill; approved changes are staged on the active feature branch." (Condensed from a full design draft that included a proposed file layout, orchestrator code, role configs, and skill wiring; the draft's implementation choices are treated as input to be validated against repo conventions, not as decided design.)

## Clarifications

### Session 2026-07-10

- Q: When a phase-2 run fails (ceiling exhausted, critic abort, or operator cancel), what happens to candidate changes already applied to the working tree? → A: Leave them applied but unstaged; staging is reserved as the success signal (staged = critic-approved), and the loop never reverts or deletes working-tree changes on its own.
- Q: How is a run time-bounded beyond the round limit and iteration ceiling? → A: Both a configurable per-role-invocation timeout (default 10 minutes; timeout = failed call, fail-closed) and a configurable whole-run wall-clock ceiling (default 60 minutes; expiry = aborted run with report).
- Q: What retention policy applies to persisted run artifacts? → A: Keep everything — no automatic pruning; the operator manages disk manually, and the per-run directory layout must make manual pruning safe and obvious.
- Q: Which model providers can the three roles run on in v1? → A: Claude-only, via alias model bindings; non-Claude role bindings are explicitly out of scope for v1 (no speculative provider abstraction).
- Q: How are implementer file writes constrained? → A: Hard-confined to the target repository's working tree; a candidate attempting an out-of-tree write (absolute path or traversal) is rejected before any write and the violation is fed back as a deficiency, with repeated violations exhausting the ceiling.
- Review correction (2026-07-10, /spec-review --mode product): FR-012 restated to make the authenticated-CLI invocation seam the v1 backend, deferring a direct SDK path to Out of Scope (the prior wording implied dual backend selection the design deliberately omits); the phase-1 interaction model made explicit in Assumptions (skill-mediated continuous conversation vs manual CLI re-entry).
- Review correction (2026-07-10, /spec-review cross-reference): FR-017's out-of-tree exemption restated — its "only to their designated run-scoped locations" clause contradicted FR-010, which mandates audit records follow the repo's existing audit-logging conventions — a fixed, env-overridable, **per-tool** JSONL under the assistant home via `audit_log.sh` (precedent: `auto_issue_dev_audit.jsonl`), not a run-scoped file and not a single shared global log. Run artifacts remain run-scoped; audit records are exempted to the feature's designated per-tool audit path. Confinement of implementer-driven writes is unchanged.
- Review correction (2026-07-10, /spec-review --mode technical): four implementation-facing fixes — (1) file targets (US3 "point at the design doc") now resolve: discovery roots fall back parent-dir → git toplevel and the pointed-at file wins as the explicit spec; (2) `repo_root_of` accepts file paths; (3) staging narrowed to exactly the final approved iteration's candidate paths — earlier rejected iterations' leftovers stay applied-but-unstaged and are reported with discard steps (FR-011 "staged = critic-approved" made literal); (4) the per-repo run lock moved from `/tmp` under the state root and FR-017 restated to name run-coordination state as a permitted out-of-tree write. Round 2: (5) a superpowers design-doc file target pairs its plan within its own layout tree (a co-existing speckit layout no longer mispairs); (6) staging skips phantom paths (created then deleted within the run, never tracked) instead of dying on the pathspec; (7) leftovers from rejected iterations are deliberately NOT auto-reverted (clarification Q1) — instead each implementer prompt discloses all loop-written files so obsolete ones can be removed via delete blocks; (8) pre-images of every file the loop overwrites/deletes are backed up per iteration (`iterations/<n>/backup/`) — the `--allow-dirty` rollback path; (9) `answer`/`status --run` locate the run by id under the state root, so they work from outside the target repo. Round 3: (10) file-target pairing moved INTO the shared discovery seam (`discover_artifacts` now handles file roots) so no second discovery mechanism exists (FR-001 kept literal; reference doc updated); (11) failure-report discard instructions restore pre-run content from the per-iteration backups instead of `git checkout` (which would destroy uncommitted `--allow-dirty` edits); (12) candidate paths containing backslashes are rejected outright (pseudo-traversal hygiene per llm-audit-traversal). Round 4: (13) `audit_log.sh` gained a generic `AUDIT_LOG_FILE` env (legacy `AUTO_ISSUE_DEV_AUDIT_FILE` still honored) so CDDL's audit stream targets its own per-tool file through the shared writer without aliasing another feature's variable; task/contract descriptions synced to the review-driven behaviors (backups, phantom staging, disclosure, run-id lookup, seam file targets); (14) role `model` values validated against the contract alias set (haiku|sonnet|opus) at pre-flight. Panel findings refuted with test evidence and left unchanged: verification cwd (already repo_root, test-pinned), lock release (try/finally + stale reclaim, test-pinned), created-file discard instructions (rm -f emitted, test-pinned), between-iteration auto-revert (contradicts clarification Q1).
- Design correction (2026-07-10, /speckit-plan research D3): role definitions deploy under the Manifest-owned prompts namespace via the standard deploy — NOT into the shared assistant agent registry, and with no new enable/disable toggle. Rationale: files in the agent registry are auto-registered as invocable assistant subagents (an unwanted side effect for subprocess role prompts), and the prompts namespace already carries the needed guarantees (repo-owned, redeploy-safe, user files never deleted). SC-008 and the two deployment edge cases were restated in those terms; FR-014's guarantees are unchanged in substance.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Critic-gated implementation of a speckit feature (Priority: P1)

A maintainer has a completed `spec.md` and `plan.md` for a feature and wants the implementation produced by a dedicated implementer role and independently approved by two adversarial critics — one focused on QA/security (input validation, boundary states, error handling), one on architecture (layering, decoupling, DRY) — before the work is considered done. They invoke a single command with the feature directory. When the run succeeds, the working tree holds the approved changes, staged on the current feature branch, and the run report records both critics' explicit approval.

**Why this priority**: This is the core value proposition — replacing single-pass, self-reviewed implementation with adversarially reviewed implementation. Without it, no other story matters; with only it, the feature is already a viable MVP.

**Independent Test**: Run the loop against a small fixture feature (spec + plan) on a scratch feature branch. Verify staged (uncommitted) changes exist, the run report records explicit approval from both critics for the final iteration, and no commit, push, or merge occurred.

**Acceptance Scenarios**:

1. **Given** a speckit feature directory containing `spec.md` and `plan.md`, a clean working tree, and a checked-out feature branch, **When** the operator runs the loop and both critics approve within the iteration ceiling, **Then** the resulting changes are staged on the current branch and the run ends with success status and both verdicts recorded.
2. **Given** the same setup, **When** a critic rejects the candidate change in iteration N, **Then** iteration N+1's implementer context contains that critic's specific findings, and the loop continues within the ceiling.
3. **Given** a run that ended successfully, **When** the operator inspects git state, **Then** no commit, push, or merge was performed by the loop.

---

### User Story 2 - Clarification gate before any code (Priority: P2)

A maintainer starts the loop on a spec that still has holes (unstated limits, unresolved structural choices). Before any implementation happens, both critics independently interrogate the spec and plan; their open questions are presented to the operator; the operator's answers are recorded into the durable run context. Implementation begins only when both critics explicitly and independently signal that no open questions remain.

**Why this priority**: The gate is what makes the loop cheap to trust — defects caught as questions cost one prompt; the same defects caught as code cost implementation iterations. It is also the primary interactive touchpoint of the feature.

**Independent Test**: Feed a fixture spec containing a deliberately ambiguous requirement. Verify the loop surfaces critic questions, produces no implementation output before the gate passes, and persists the operator's answers into the run context used by later phases.

**Acceptance Scenarios**:

1. **Given** a spec with a deliberately ambiguous requirement, **When** the loop starts, **Then** the critics' open questions are presented to the operator and no implementation output of any kind exists before the gate passes.
2. **Given** the operator has answered the open questions, **When** both critics re-analyze and each independently signals completion, **Then** phase 2 begins and the recorded answers are part of every subsequent iteration's context.
3. **Given** critics still report open questions when the configured clarification-round limit is reached, **When** the limit is hit, **Then** the run ends with an explicit gate-failure report listing the unresolved questions, and no code was produced.

---

### User Story 3 - Same loop over a superpowers doc pair (Priority: P3)

A maintainer working in the superpowers layout (a design doc plus a matching implementation plan, with tasks embedded in the plan rather than in a separate file) points the same command at their design doc. The loop resolves the paired artifacts, and everything else behaves identically to the speckit case.

**Why this priority**: Dual-workflow support is what makes this a repo-wide capability rather than a speckit-only bolt-on, but it builds entirely on the P1/P2 machinery.

**Independent Test**: Run the loop against a fixture superpowers design doc with a paired plan. Verify the run resolves both artifacts, completes the same phases, and never reports a missing tasks artifact.

**Acceptance Scenarios**:

1. **Given** a superpowers design doc and a paired plan, **When** the operator invokes the loop with the design doc path, **Then** the loop resolves spec and plan per the repo's artifact-discovery precedence and runs identically to the speckit case.
2. **Given** a superpowers-layout run, **When** the run produces any report or error, **Then** it never reports a missing tasks artifact.
3. **Given** a target path matching neither layout, **When** the operator invokes the loop, **Then** the run refuses during pre-flight with an actionable error naming the two supported layouts, and no model calls or state mutations occur.

---

### User Story 4 - Diagnosable run history (Priority: P4)

A maintainer whose run failed (for example, at the iteration ceiling) opens the run's persisted artifacts and identifies which critic blocked, on what deficiency, at which iteration — without re-running anything.

**Why this priority**: Failed runs are expected in an adversarial loop; without cheap diagnosis, every failure costs a full re-run and the feature becomes too expensive to trust.

**Independent Test**: Force a run to fail at a low iteration ceiling. Verify the persisted run artifacts identify the blocking critic and its outstanding findings for the final iteration, without re-running.

**Acceptance Scenarios**:

1. **Given** any completed or failed run, **When** the operator inspects the run's persisted artifacts, **Then** each iteration has the implementer output, both critics' verdicts and findings, and timestamps.
2. **Given** a run that failed at the iteration ceiling, **When** the operator reads the final report, **Then** it lists the outstanding deficiencies per critic for the last iteration.
3. **Given** clarification answers were recorded in phase 1, **When** phase 2 iterations are persisted, **Then** those answers appear in each iteration's persisted context.

---

### Edge Cases

- **Unresolvable target**: The target path matches neither layout → pre-flight refusal with an actionable error (per FR-001); no model calls, no working-tree or state mutation.
- **Layout ambiguity**: A target could plausibly match both layouts → the repo's existing discovery precedence (explicit paths > speckit > superpowers) decides, and the resolved choice is recorded in the run log (per FR-001).
- **Missing plan**: Spec resolves but no plan artifact exists → the run proceeds with spec-only context, records the absence, and discloses it to the critics rather than failing or silently pretending a plan exists.
- **Verdict spoofing**: A critic's prose mentions an approval phrase while actually rejecting (e.g., quoting "LGTM" inside a criticism) → this MUST NOT register as approval; verdicts are structured and fail-closed (per FR-006).
- **Critic failure**: A critic invocation errors, times out, or returns an empty/unparseable response → bounded retries, and an unrecoverable critic aborts the run fail-closed; a dead critic never counts as approval (per FR-006).
- **Never-converging critics**: Critics keep rejecting → the iteration ceiling ends the run with a failure report and a distinct failure status (per FR-008); never an unbounded loop, never silent truncation.
- **Implementation stall**: An iteration produces no substantive change relative to the previous one → the iteration still counts toward the ceiling and the stall is flagged in the run report; a stall is never reported as success.
- **Dirty working tree**: Uncommitted changes exist at start → pre-flight refusal unless the operator explicitly overrides, so loop-produced changes never mix with unrelated edits (per FR-011).
- **Default-branch invocation**: The current branch is the default branch → pre-flight refusal; the loop only ever writes to a non-default feature branch (per FR-011).
- **No authenticated model access**: No usable backend is available for a required role → fail fast during pre-flight with an actionable authentication message; no partial run (per FR-012).
- **Interrupted run**: The process dies or is cancelled mid-run → already-persisted per-iteration artifacts survive for diagnosis, and any applied candidate remains in the working tree unstaged (per FR-011); the report/log makes the incomplete state evident (resume is out of scope).
- **Missing or invalid role definition**: A role definition file is absent or malformed → fail fast during pre-flight, before any model call (per FR-013).
- **Out-of-tree write attempt**: An implementer candidate specifies a file path outside the target repository's working tree (absolute, `..` traversal, or symlink escape) → the candidate is rejected before any write, the violation is recorded as a deficiency, and repeated attempts exhaust the ceiling (per FR-017).
- **Deploy-time registry safety**: Deployment writes zero files into the shared assistant agent registry — role prompts land only in the Manifest-owned prompts namespace, so no new assistant subagents are registered and no user-owned agent file can be collided with or overwritten (per FR-014).
- **Redeploy with operator customizations present**: A re-deploy over a home where the operator added their own files near the role prompts → operator files survive (the deploy never deletes user-added files); Manifest-owned role files reconverge to the repo state; retiring the feature removes its assets via the established deploy-reconcile flow with nothing else touched (per FR-014).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The feature MUST provide a single entry point that accepts one target path and supports both speckit feature directories and superpowers design docs, resolving the spec and plan artifacts according to the repo's existing spec-artifact discovery contract (explicit paths win, then speckit detection, then superpowers fallback). It MUST NOT introduce a second, divergent discovery mechanism.
- **FR-002**: The loop MUST NOT require a tasks artifact: superpowers runs (where tasks are embedded in the plan) MUST never be reported as missing tasks, and speckit runs MUST work with spec and plan alone.
- **FR-003**: Phase 1 (clarification gate): both critic roles MUST independently analyze the resolved spec+plan context; open questions MUST be presented to the operator; operator answers MUST be appended to a durable run context; and phase 2 MUST NOT begin until each critic has independently produced an explicit, machine-checkable completion signal.
- **FR-004**: The clarification gate MUST be bounded by a configurable round limit (default: 3 rounds). On exhaustion with open questions remaining, the run MUST end with a gate-failure report listing the unresolved questions, without producing any implementation output.
- **FR-005**: Phase 2 (implementation loop): a dedicated implementer role MUST produce the candidate change; each critic MUST audit the candidate independently (QA/security: input validation, boundary states, error handling, runtime safety; architecture: design adherence, layering, decoupling, DRY); and a run may end successfully only when every critic has explicitly approved the same iteration's candidate.
- **FR-006**: Verdict integrity: critic completion and approval signals MUST be structured and unambiguous such that a mention of the signal inside critique prose cannot register as approval, and any missing, malformed, or unparseable critic response MUST be treated as non-approval (fail-closed), with bounded retries before aborting the run.
- **FR-007**: Deficiency feedback: when any critic rejects an iteration, all critics' findings from that iteration MUST be included in the next iteration's implementer context, and the full findings history MUST be retained for the run's duration and its persisted record.
- **FR-008**: The implementation loop MUST be bounded by a configurable iteration ceiling (default: 10). On exhaustion without dual approval, the run MUST end with a distinct failure status and a report of the outstanding deficiencies per critic — never silently and never unbounded. In addition, every role invocation MUST be bounded by a configurable timeout (default: 10 minutes), with a timed-out invocation treated as a failed call (fail-closed per FR-006), and the whole run MUST be bounded by a configurable wall-clock ceiling (default: 60 minutes) whose expiry aborts the run with a report.
- **FR-009**: Verification before critique: within each iteration, the candidate change MUST pass the project's own verification gates (tests and lint for the target project, where they exist) before being submitted for critic audit; verification failures MUST feed back into the next iteration as deficiencies without being presented to critics as review-ready work.
- **FR-010**: Run persistence: every run MUST persist, per iteration, the inputs, implementer output, each critic's verdict and findings, and timestamps, under a run-scoped location, such that an operator can identify the blocking critic and deficiency for any failed run without re-running. Run artifacts are retained indefinitely — the loop MUST NOT auto-prune them; each run MUST live in a self-contained per-run directory so manual pruning by the operator is safe and obvious. Run lifecycle events MUST also append to an audit record consistent with the repo's existing audit-logging conventions (fail-open: audit failure never blocks the run).
- **FR-011**: Git safety: the loop MUST refuse to start on the repository's default branch and MUST refuse to start on a dirty working tree unless the operator explicitly overrides; produced changes MUST be applied to the working tree of the current feature branch only, and staging MUST occur only on run success (staged = critic-approved). On failure or abort, the final candidate change MUST remain applied but unstaged, with the run report stating how to discard it; the loop MUST NOT revert or delete working-tree changes on its own, and MUST NOT commit, push, merge, or open pull requests.
- **FR-012**: Model access: all role invocations MUST use the operator's existing authenticated model access. In v1 this is the operator's authenticated Claude CLI behind an overridable invocation seam, with all three roles on Claude backends only and models referenced by alias (per FR-013); a direct SDK backend is deferred (see Out of Scope). The feature MUST NOT hard-require a raw API key, and a missing usable backend MUST fail fast during pre-flight.
- **FR-013**: Roles as configuration: the three roles (implementer, QA/security critic, architecture critic) MUST be defined in editable per-role definition files following the repo's existing agent-definition conventions (structured frontmatter for name/description/model plus a prompt body, with models referenced by alias). Operators MUST be able to tune a role's prompt or model without code changes, and missing/invalid definitions MUST fail pre-flight (see Edge Cases).
- **FR-014**: Deployment safety: role definitions and any deployed assets MUST be Manifest-owned and cleanly removable, and their deployment MUST NOT weaken the guarantees established for the existing agent-deployment mechanism (ownership marker, pre-deploy collision guard, sole-writer gating, byte-identical homes when disabled). New role names MUST NOT collide with the six existing pilotfish role-agent names.
- **FR-015**: Skill registration: the user-facing entry point MUST be a skill named per the repo taxonomy for dual-workflow spec skills (spec-* prefix, purpose-first pattern), created in the skills source of truth, registered with a tool-policies entry, with derived artifacts regenerated, and its frontmatter MUST fit the always-loaded context budget measured at deployed size.
- **FR-016**: Failure transparency and script conventions: every abnormal end state (unresolvable target, missing backend, gate failure, ceiling exhaustion, aborted critic, interrupted run) MUST produce a distinct, actionable message; errors MUST propagate rather than being logged and dropped; and the entry-point script MUST follow the repo's script conventions (including `--help` and stderr error routing).
- **FR-017**: Write confinement: all file writes driven by implementer output MUST be confined to the target repository's working tree. A candidate specifying a write outside it (absolute path, upward traversal, or symlink escape) MUST be rejected before any write occurs, with the violation recorded and fed back as a deficiency (per FR-007); run artifacts, run-coordination state (the per-repo run lock under the state root), and audit records (per FR-010) are the only writes permitted outside the working tree — run artifacts only to their designated run-scoped locations, coordination state only under the state root, audit records only to this feature's designated audit-log file (the repo's audit-logging convention, per FR-010, is a fixed, env-overridable, per-tool JSONL under the assistant home — not a run-scoped file and not a single shared global log).

### Key Entities

- **Feature Context**: The normalized input to a run — resolved spec content, plan content (possibly absent, with absence recorded), layout type, and accumulated clarification answers.
- **Role Definition**: An editable definition of one loop participant (implementer, QA/security critic, architecture critic) — identity, model binding by alias, and system prompt.
- **Run**: One invocation of the loop over one Feature Context — phases, iterations, final status (success, gate failure, ceiling failure, aborted), and report.
- **Iteration**: One phase-2 cycle — candidate change, verification result, one Verdict per critic, and timestamps.
- **Verdict**: A single critic's structured judgment of one iteration (or of the phase-1 gate) — approve/reject (or complete/questions), plus findings; unparseable means non-approval.
- **Clarification Exchange**: One phase-1 round — critic questions, operator answers, and the resulting context amendment.
- **Deficiency**: A single actionable finding from a critic or from project verification, attributed to its source and iteration, fed into the next iteration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can start a run on either supported layout with a single command and zero manual context assembly (no copying spec/plan content by hand), in both a speckit and a superpowers fixture.
- **SC-002**: 100% of runs terminate in bounded time with one of the defined end states (success, gate failure, ceiling failure, aborted) and an explicit report; zero unbounded or silently-ended runs across the test suite, including forced never-converge fixtures.
- **SC-003**: 100% of successful runs have recorded, independent, structured approval from both critics for the final iteration; a spoofing fixture (approval phrase quoted inside a rejection) produces zero false approvals.
- **SC-004**: For any failed run, an operator can identify the blocking critic and its top outstanding deficiency from the persisted artifacts in under 5 minutes, without re-running.
- **SC-005**: Zero runs mutate the default branch, create commits, or publish changes; across the test suite, every staged change belongs to a critic-approved successful run on a non-default branch, and every failed run leaves its candidate unstaged. Zero loop-driven writes land outside the target repository's working tree, including against traversal fixtures.
- **SC-006**: In every iteration of every run where the target project has verification gates, the candidate presented to critics already passes those gates — critics spend zero review cycles on changes that fail the project's own tests.
- **SC-007**: After registration, all existing repository quality gates remain green — naming-taxonomy gate, context-budget gate (at deployed size), and derived-docs consistency — with no cap raises beyond documented headroom.
- **SC-008**: The deployment-safety suite passes for FR-014: deployment registers zero new assistant subagents (the shared agent registry is byte-identical before and after), 100% of operator-added files in the deployed home survive a redeploy, and retiring the feature removes 100% of the Manifest-owned role assets and nothing else.

## Assumptions

- **Verification-before-critique is in scope (decided)**: The design draft left "run the project's tests before critic review" as an open question; this spec decides yes (FR-009) — the repo's test-first culture and the issue-dev-auto precedent make review-of-red-builds wasteful.
- **Persistent run snapshots are in scope (decided)**: The draft's second open question (per-iteration debug/state dumps) is decided yes (FR-010); diagnosability is what keeps an adversarial loop affordable (User Story 4).
- **Skill naming and placement**: The draft's `speckit-loop-dev` name and project-local skills-dir placement are superseded by repo conventions: dual-workflow spec skills use the `spec-` prefix (precedent: the speckit-audit-tasks → spec-audit-tasks rename) and live in the skills source of truth (`.skillshare/skills/`). Working name: `spec-implement-loop`; final name is subject to the naming gate (FR-015).
- **Model access**: The draft's direct-SDK-with-API-key design is treated as illustrative; v1 invokes the operator's authenticated Claude CLI behind an overridable seam (FR-012), since operator machines commonly have subscription CLI auth and no raw API key. An SDK backend is deferred, not precluded.
- **Role definition format**: The draft's standalone YAML role files with hardcoded model IDs are treated as illustrative; role definitions follow the repo's existing agent-definition format with alias-based model bindings (FR-013).
- **Defaults**: Iteration ceiling defaults to 10 (from the draft) and clarification rounds to 3; per-invocation timeout defaults to 10 minutes and the whole-run wall-clock ceiling to 60 minutes; all are configurable (FR-004, FR-008).
- **Operator presence**: Phase 1 is interactive; the operator is assumed available to answer clarification questions during the run. There is no long-lived blocking prompt: when run via the mediating skill, the operator experiences the gate as one continuous conversation (the skill relays critic questions and re-enters the loop with the answers); when driving the command directly, each clarification round is a manual re-entry. Unattended operation is out of scope.
- **Relationship to existing commands**: The loop is an alternative, critic-gated implementation path that complements `/speckit-implement`; it does not replace it or alter the existing speckit lifecycle hooks.

## Out of Scope

- **Merging, pushing, PR creation, or PR babysitting** — the run ends at staged changes (per FR-011); existing skills (issue-dev-auto's merge loop, pr-monitor) own everything after that.
- **Resuming interrupted runs** — persisted artifacts support diagnosis (per FR-010), but restart-from-iteration is deferred.
- **Multi-provider critic panels and consensus scoring** — this is a sequential role loop with unanimous structured verdicts, deliberately distinct from the parallel-agent consensus machinery; critics are not parallel_agent providers, and non-Claude role bindings are deferred (v1 is Claude-only per FR-012).
- **Deployment to non-Claude assistant homes** (Cursor, Gemini, Codex, Antigravity) — following the feature-481 precedent, role definitions target the Claude home only in v1.
- **Unattended/CI operation** — the phase-1 gate requires an operator (per Assumptions); headless operation would need a different clarification policy and is deferred.
- **Direct SDK backend for role invocations** — v1 uses the authenticated CLI seam only (per FR-012); adding an SDK path for API-key-configured environments is deferred.
