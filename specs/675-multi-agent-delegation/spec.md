# Feature Specification: Multi-Agent Delegation Plugin

**Feature Branch**: `675-multi-agent-delegation`

**Created**: 2026-08-05

**Status**: Draft

**Input**: User description: "Create a plugin that leverages https://github.com/openai/codex-plugin-cc/tree/main/plugins as a baseline. Generate a complete plugin doing the same with claude, codex, agy."

## Clarifications

### Session 2026-08-05

- Q: How should the new multi-backend plugin relate to the existing codex plugin? → A: Supersede — the new repo-native bundle absorbs the baseline codex plugin's capabilities and replaces it in this workspace, with a migration note. (Baseline research subsequently established the codex plugin is externally installed from the marketplace, not vendored in this repo — so "retire" means the workspace stops depending on the external plugin; the third-party plugin itself is untouched.)
- Q: Default backend when none is named? → A: Codex, overridable via a user-level configuration file in the user's home configuration directory that supports at least the default backend, enabling/disabling backends, and per-backend model selection.
- Q: Is the backend set a closed set of three, or extensible? → A: Extensible registry seeded with exactly Claude, Codex, and Antigravity; adding a future backend must be a registry entry + readiness probe, not a redesign. Shipped scope remains the three.
- Q: Default delegation time budget? → A: 600 seconds, overridable per invocation and per backend via the user configuration file.
- Q: Review gate semantics — advisory or blocking? → A: Soft gate — completion pauses at most once, bounded by the gate's time budget; findings are presented and the developer decides; the gate never loops and never auto-applies fixes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Delegate a task to a chosen agent backend (Priority: P1)

A developer working in their primary coding session wants to hand a substantial task — an implementation, an investigation, or a diagnosis — to one of the supported external coding agents (Claude, Codex, or Antigravity) and receive the outcome back in their session without leaving it. The baseline plugin provides this "rescue/delegate" capability for Codex only; this feature provides the same capability uniformly across all three backends, with the backend chosen explicitly by the developer or by a sensible default.

**Why this priority**: Delegation is the core value of the baseline plugin. Without it, none of the other capabilities matter. It is also the only story that exercises all three backends end to end.

**Independent Test**: Can be fully tested by invoking the delegation entry point three times — once per backend — with a small, self-contained coding task, and confirming each returns a usable result (or an actionable error if that backend is not ready) inside the originating session.

**Acceptance Scenarios**:

1. **Given** a ready Codex backend, **When** the developer delegates a task and names Codex, **Then** the task runs on Codex and a summarized result (outcome, changes, follow-ups) is returned in the session.
2. **Given** a ready Claude backend, **When** the developer delegates the same task and names Claude, **Then** the task runs on a separate Claude instance and an equivalently structured result is returned.
3. **Given** a ready Antigravity backend, **When** the developer delegates the same task and names Antigravity, **Then** the task runs on Antigravity and an equivalently structured result is returned.
4. **Given** no backend is named, **When** the developer delegates a task, **Then** the plugin selects the configured default backend (Codex out of the box) and states which backend it used.
5. **Given** a backend that is not installed or not authenticated, **When** the developer delegates to it, **Then** the plugin reports the specific gap, names the fix, and offers the other ready backends — it never fails silently or pretends the task ran.

---

### User Story 2 - Verify backend readiness (Priority: P2)

A developer (or a fresh machine setup) wants a single check that reports, for each of the three backends: is it installed, is it authenticated, and is it ready to accept delegated work — with concrete remediation steps for anything missing. The baseline plugin provides this for Codex ("setup"); this feature provides the same check for all three backends in one place.

**Why this priority**: Every delegation depends on backend readiness. A uniform readiness report converts the most common failure mode (missing/unauthenticated CLI) from a mid-task surprise into an upfront, fixable finding.

**Independent Test**: Run the readiness check on a machine where at least one backend is ready and at least one is not; confirm the report distinguishes the two states and gives an actionable fix for the unready one.

**Acceptance Scenarios**:

1. **Given** all three backends installed and authenticated, **When** the readiness check runs, **Then** it reports all three as ready with their versions/identities.
2. **Given** one backend missing, **When** the readiness check runs, **Then** it reports that backend as unavailable with the exact installation step, while still reporting the others as ready.
3. **Given** a backend installed but not authenticated, **When** the readiness check runs, **Then** it reports the authentication gap and the exact login step, without blocking on interactive input.

---

### User Story 3 - Second opinion across agents (Priority: P3)

A developer whose primary agent is stuck — a bug it cannot find, a diagnosis it is unsure of — wants to hand the same context to a *different* agent backend for an independent pass, then see the second agent's findings alongside the first. The baseline plugin frames this as "rescue" (Codex rescues Claude); this feature generalizes it: any ready backend can provide the second pass.

**Why this priority**: Cross-verification is this repository's core working method. Extending rescue from one fixed pair (Claude→Codex) to any pair multiplies the paths out of a stuck state, but it builds entirely on Story 1's delegation plumbing.

**Independent Test**: Present a small diagnostic task with a known answer, get a first-pass result from one backend, then invoke the second-opinion flow targeting a different backend; confirm the second pass runs with the shared context and the two results are presented for comparison.

**Acceptance Scenarios**:

1. **Given** a completed or stuck first attempt, **When** the developer requests a second opinion and names a different backend, **Then** the second backend receives the task context and its independent findings are returned and clearly attributed.
2. **Given** the named second backend is the same as the first, **When** the developer requests a second opinion, **Then** the plugin warns that the pass is not independent and offers the other backends.

---

### User Story 4 - Optional finish-time review gate (Priority: P4)

A developer wants an optional, off-by-default gate: when their primary session declares work complete, a chosen backend reviews the pending changes and reports findings before the work is considered done. The baseline plugin offers a toggleable stop-time review gate backed by Codex; this feature offers the same gate with the reviewing backend selectable among the three.

**Why this priority**: Valuable but optional polish; it layers on Stories 1–2 and mirrors an explicitly toggleable baseline capability rather than a default behavior.

**Independent Test**: Enable the gate with a chosen review backend, complete a small change, and confirm the review runs and its findings are surfaced; disable the gate and confirm no review runs.

**Acceptance Scenarios**:

1. **Given** the gate is enabled with backend X, **When** the session declares work complete, **Then** completion pauses once — bounded by the gate's time budget — while backend X reviews the pending changes, and the findings are presented for the developer to decide on.
2. **Given** the gate is disabled (default), **When** the session declares work complete, **Then** no review runs and completion is not delayed.
3. **Given** the gate is enabled but the chosen backend is unready, **When** completion is declared, **Then** the gate reports the gap and does not block completion indefinitely.

---

### Edge Cases

- Backend CLI present but wrong/retired version (e.g., a backend whose CLI was superseded): readiness must detect and say so rather than invoking a dead tool.
- Delegated task exceeds the backend's or session's time budget: the plugin must time out cleanly, report partial state, and leave no orphaned processes.
- Backend returns malformed or empty output: result handling must surface "backend returned nothing usable" rather than fabricating a summary.
- Two delegations invoked concurrently in one session: results must not interleave or overwrite each other's context.
- Backend attempts destructive operations (force push, deletes) inside the delegated task: delegation must run backends in their non-interactive, restricted mode and must not grant approval on the user's behalf.
- The user's workspace has a backend disabled by configuration: delegation and readiness must respect the disable toggle rather than invoking a deliberately disabled service.
- Very large task context (bigger than a backend accepts): the plugin must state the limit rather than silently truncating.
- Configuration file present but malformed or unreadable: the plugin reports the problem and proceeds on documented factory defaults — it neither crashes nor silently honors a broken configuration.
- User configuration enables a backend the workspace has disabled: the workspace disable wins, and the readiness/delegation report names which layer blocked it.
- Configuration or invocation names a backend that is not in the registry: the plugin rejects it and lists the known backends, rather than guessing or ignoring the entry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The plugin MUST let a developer delegate a self-contained task to any one of three agent backends — Claude, Codex, or Antigravity (agy) — from within their primary session, using one uniform entry point where the backend is a parameter.
- **FR-002**: The plugin MUST return delegated results in a consistent structure across backends: what was attempted, what changed, what succeeded/failed, and recommended follow-ups — so a developer can read any backend's result the same way.
- **FR-003**: The plugin MUST provide a readiness check covering all three backends that reports installed/authenticated/ready status per backend and names the exact remediation for any gap, without requiring interactive input.
- **FR-004**: When a requested backend is unavailable (missing, unauthenticated, disabled, or retired), the plugin MUST fail loudly with the specific cause and offer ready alternatives; it MUST NOT fall back silently to a different backend.
- **FR-005**: The plugin MUST support a second-opinion flow: re-running a task's context on a different backend than the one that produced the first result, with the two results clearly attributed.
- **FR-006**: The plugin MUST provide an optional finish-time review gate, disabled by default, whose reviewing backend is selectable among the three, and which can be enabled/disabled through the user configuration file without reinstalling. The gate is a soft gate: it pauses completion at most once per completion attempt, bounded by its time budget, presents its findings for the developer to decide on, and never loops or auto-applies fixes.
- **FR-007**: The plugin MUST apply backend-appropriate prompt guidance when delegating (each backend has its own prompting conventions), preserving the baseline plugin's per-model prompting quality for Codex and matching it for the other two backends.
- **FR-008**: The plugin MUST run backends non-interactively and within each backend's restricted/sandboxed execution mode; write access is granted only when the developer asks for it. It MUST NOT auto-approve destructive actions, widen a backend's permissions beyond what the user configured, or auto-apply fixes surfaced by a review (the baseline's hard non-autonomy rule is preserved).
- **FR-009**: The plugin MUST respect the workspace's service enable/disable toggles for each backend and the workspace's model-selection policy (delegated sub-work defaults to the configured economical model; premium models only on explicit request).
- **FR-010**: The plugin MUST be packaged and registered like the repository's existing plugin bundles — discoverable in the plugin catalog, listed in generated documentation, and installable through the same marketplace mechanism — so it appears alongside existing bundles with no bespoke install path.
- **FR-011**: The plugin MUST supersede the externally installed baseline codex plugin in this workspace: every user-facing capability of the baseline MUST be available in the new bundle, a migration note MUST map each baseline entry point to its replacement, and the workspace MUST operate fully with the external plugin uninstalled. At no point during the transition may a capability be unavailable in both.
- **FR-014**: Delegations MUST be able to run in the background: the developer can continue working, then check a delegation's status, fetch its result, or cancel it — matching the baseline plugin's job-management capability across all three backends.
- **FR-015**: A follow-up to a prior delegation MUST continue that delegation's conversation where the backend supports resumable sessions; where a backend cannot resume, the plugin MUST say so and re-send the necessary context rather than silently starting fresh. The plugin MUST also support handing the current session's task context over to a backend session for continuation (the baseline's "transfer" capability), for every backend that can accept it.
- **FR-012**: All delegation, readiness, and review operations MUST propagate errors with actionable messages (never log-and-drop), and time budgets MUST be enforced with clean process termination. The default delegation time budget is 600 seconds, overridable per invocation and per backend via the user configuration file.
- **FR-013**: The plugin MUST read a user-level configuration file from the user's home configuration directory supporting, at minimum: the default backend (factory default: Codex), enabling/disabling individual backends, and per-backend model selection. Changes MUST take effect on the next invocation without reinstalling. When the file is absent, documented factory defaults apply (Codex default, all three backends enabled). When the file is unreadable or invalid, the plugin MUST report the problem and proceed on factory defaults rather than guessing. Workspace-level service disables take precedence over user-level enables.
- **FR-016**: Backends MUST be modeled as uniform entries in an extensible backend registry. The shipped registry contains exactly Claude, Codex, and Antigravity, but the delegation, readiness, second-opinion, review-gate, and configuration surfaces MUST be backend-generic, so that adding a future backend requires only a new registry entry (identity, readiness probe, invocation and prompting conventions) — no redesign of any existing surface. Session-transfer support is declared per entry from the registry's fixed transfer-method vocabulary; a backend fitting an existing method is covered by this entry-only guarantee, while introducing a wholly new transfer protocol is a deliberate dispatcher extension outside it.

### Key Entities

- **Agent Backend**: One entry in the extensible backend registry — shipped entries are the three supported external coding agents (Claude, Codex, Antigravity). Attributes: identity, readiness state (installed/authenticated/ready/disabled/retired), invocation conventions, prompting conventions.
- **Delegation Request**: A self-contained unit of work handed to a backend: task description, relevant context, time budget, and the chosen backend.
- **Delegation Result**: The normalized outcome of a request: attempted actions, changes made, success/failure signals, follow-up recommendations, and the backend that produced it.
- **Readiness Report**: Per-backend status snapshot with remediation steps for any gap.
- **Review Gate Configuration**: Whether the finish-time gate is on, and which backend reviews.
- **User Configuration**: The user-level settings governing delegation — default backend, per-backend enabled state, per-backend model selection, per-backend time budgets, and review-gate settings. Lives in the user's home configuration directory; documented factory defaults apply when it is absent.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can delegate the same small task to each of the three backends and receive a structured result from every ready backend, in 100% of attempts, without leaving their session.
- **SC-002**: Capability parity with the baseline is complete: every user-facing capability of the baseline codex plugin (delegate/rescue with resumable follow-ups, setup check, foreground/background review including adversarial mode, job status/result/cancel, session transfer, result handling, prompting guidance, optional review gate) has a working equivalent for all three backends, verified by a traceability check with zero uncovered baseline capabilities.
- **SC-003**: The readiness check completes in under 30 seconds and, for any unready backend, names a remediation that resolves the gap without further investigation for every enumerated failure class in the fault-injection matrix (missing binary, not logged in, disabled by configuration — workspace and user layers), each class validated by its fault test.
- **SC-004**: Zero silent failures: in fault-injection tests (missing backend, timeout, malformed output, disabled service), 100% of failures produce an explicit, attributed, actionable message.
- **SC-005**: The new plugin appears in the plugin catalog and generated documentation identically to existing bundles, and a fresh workspace can install and invoke it using only the standard marketplace flow.
- **SC-006**: After supersession, 100% of the baseline codex plugin's user-facing capabilities are reachable through the new plugin, the workspace operates with the external baseline plugin uninstalled, and the migration note maps every baseline entry point to its replacement.
- **SC-007**: A user can change the default backend, disable a backend, or change a backend's model by editing the user configuration file alone; the change is honored on the very next invocation with no reinstall, in 100% of attempts.

## Assumptions

- The baseline is the externally installed `openai/codex-plugin-cc` plugin (observed installed version 1.0.6, verified byte-identical in file inventory to upstream `plugins/codex`). It is **not** vendored in this repository. Its observed capability set — setup/install check; rescue/delegation with resumable threads; foreground and background review, including an adversarial mode, with a hard rule that review findings are never auto-applied; job management (status/result/cancel); session-to-thread transfer; result-handling conventions; model-specific prompting guidance; and an optional stop-time review gate — is the parity target. The installed version observed at implementation time is the authoritative baseline if upstream drifts.
- "Doing the same with claude" means delegating to a separate, non-interactive Claude session as an external worker — the same delegation pattern used for the other backends — not a change to the primary session itself.
- "agy" refers to the Antigravity CLI already integrated in this workspace as a provider; it is invoked non-interactively like the other backends. Retired CLIs (e.g., the former Gemini CLI) are out of scope.
- The new plugin is a repo-native bundle that supersedes the externally installed baseline plugin in this workspace (per Clarifications 2026-08-05): capabilities are absorbed first, then the workspace's dependency on the external plugin ends, with a migration note. Any coexistence is a transitional state inside the feature, never a shipped end state. The third-party plugin itself is not modified.
- The workspace's existing shared catalog constraints (description budgets, naming-taxonomy limits) apply, and because the baseline's skills live outside the repo catalog, the new bundle's entire surface is net-new against those budgets; fitting may require offsetting savings elsewhere or per-bundle budget accounting. This is a known constraint, not an open question.
- The baseline achieves job management through a persistent per-backend broker; whether the generalized plugin reproduces that mechanism or delivers the same user-facing capability another way is a planning decision. The capability (background delegation with status/result/cancel), not the mechanism, is the requirement.
- Backend authentication is handled by each CLI's own login flow; this plugin never stores or handles credentials itself.
- The default delegation time budget is 600 seconds (per Clarifications 2026-08-05), consistent with the workspace's documented convention for delegated analyses; per-invocation and per-backend overrides cover the long tail.
