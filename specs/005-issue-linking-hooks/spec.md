# Feature Specification: Issue-Linking Git Hooks

**Feature Branch**: `005-issue-linking-hooks`

**Created**: 2026-06-14

**Status**: Delivered 2026-06

**Input**: User description: "Create a skill that is designed to support / improve github / gitlab issues. Run it as a hook whenever a PR is executed. Additionally define a similar skill for branch commits."

## Clarifications

### Session 2026-06-14

- Q: What execution model should the hooks use (sync vs async vs hybrid), given they run inline with git actions? → A: **Bounded synchronous run with a soft timeout, fail-open** (Option A). Chosen for the long term because the engine is already idempotent + de-duplicated, so a timed-out run self-heals on the next trigger or a manual re-run — making a background queue (Option B) unnecessary infrastructure and an out-of-band failure-visibility liability, while preserving the interactive "offer to create issue" path. The timeout and commit execution mode are promoted to config rather than hard-coded: `hook_timeout_seconds` (default `5`) and `commit_hook_mode` (`sync` | `background`, default `sync`), so a repo can opt into background commit handling later without a redesign. Trade accepted: the first PR/commit on a branch may wait up to the timeout; dedup makes subsequent commits near-instant no-ops.
- Q: Should auto-created tracking issues be minimal stubs or best-of-breed? → A: **Best-of-breed.** Before creating, the engine MUST check the tracker for an existing matching issue and reuse it rather than duplicate. A created issue MUST use a structured template (context summary, acceptance criteria, bidirectional links to the branch/PR/commit) and the canonical label set, so an auto-created issue is indistinguishable from a well-authored one.
- Q: What is the precise issue status transition per trigger? → A: A **commit** on a branch advances a `planned` issue to `in-progress`; a **PR/MR opening** advances the linked issue to `needs-review`. Transitions only move forward (never regress an issue already further along).

## User Scenarios & Testing *(mandatory)*

This feature delivers **two companion skills** that keep the issue tracker (GitHub Issues or GitLab Issues) in sync with development activity, invoked automatically as git/platform hooks:

- A **PR-triggered** skill that runs whenever a pull/merge request is opened.
- A **commit-triggered** skill that runs whenever commits land on a feature branch.

Both share one underlying "issue-support engine" and behave **fail-open**: if the platform API is unreachable or any step errors, the developer's git action is never blocked — the skill degrades to a warning.

### User Story 1 - Auto-sync the linked issue when a PR is opened (Priority: P1)

When a developer opens a pull request (GitHub) or merge request (GitLab), a hook fires the PR-support skill. The skill identifies the issue(s) the PR relates to, posts a back-link comment on each issue, advances the issue's status label to `needs-review` (regardless of current stage, forward-only — see FR-006a), and verifies the PR description contains the correct closing keyword (e.g., `Closes #17`). All actions are advisory-safe: a failure warns but never aborts PR creation.

**Why this priority**: This is the core value — it eliminates the manual, frequently-forgotten step of keeping issues current when work reaches review. It is the smallest slice that delivers a working, demonstrable MVP on its own.

**Independent Test**: Open a PR on a branch associated with a known issue; confirm the issue receives a back-link comment, its status label advances, and a missing closing keyword is reported — without any manual issue edits.

**Acceptance Scenarios**:

1. **Given** a PR is opened on a branch tied to issue #17, **When** the PR-support hook runs, **Then** issue #17 receives a comment linking to the PR and its status label advances to the review stage.
2. **Given** a PR body that omits a closing keyword for its linked issue, **When** the hook runs, **Then** the skill ensures/inserts the correct `Closes #<n>` reference (or warns if it cannot edit the PR body).
3. **Given** the issue tracker API is unreachable, **When** the hook runs, **Then** the PR is still created successfully and the developer sees a non-blocking warning.
4. **Given** a PR references multiple issues, **When** the hook runs, **Then** each referenced issue is updated independently.

---

### User Story 2 - Auto-sync the linked issue on branch commits (Priority: P2)

When a developer commits to a feature branch, a hook fires the commit-support skill. Using the same engine, it associates the commit(s) with the relevant issue and keeps that issue current — e.g., moving a freshly-started issue from `planned` to `in-progress` and (optionally) appending a lightweight progress reference. It de-duplicates so the same issue is not spammed on every commit.

**Why this priority**: Extends the same value earlier in the lifecycle (work-in-progress visibility) so an issue reflects "active" status as soon as real work begins, not only at PR time. Depends on the shared engine proven in P1.

**Independent Test**: Commit to a branch tied to a `planned` issue; confirm the issue advances to `in-progress` exactly once across multiple commits, and that the hook never blocks the commit.

**Acceptance Scenarios**:

1. **Given** a commit lands on a branch tied to a `planned` issue, **When** the commit-support hook runs, **Then** the issue advances to `in-progress`.
2. **Given** several further commits on the same branch, **When** the hook runs each time, **Then** the issue is not repeatedly commented on or re-transitioned (idempotent / de-duplicated).
3. **Given** a commit on a branch with no resolvable issue association, **When** the hook runs, **Then** the commit-support flow defers to the missing-issue behavior (User Story 3) without blocking the commit.

---

### User Story 3 - Offer to create a tracking issue when none is linked (Priority: P3)

When either skill cannot resolve a linked issue (no branch-number prefix, no reference in the PR body or commit messages), it offers to create a tracking issue, pre-filled from the available context (branch name, PR title/body, or commit subject). The issue is created **only on explicit confirmation**; declining proceeds with a warning.

**Why this priority**: Closes the gap for ad-hoc work that started without an issue, but is independent of the core sync and safe to ship later. Creation-on-confirm keeps it from generating tracker noise.

**Independent Test**: Open a PR (or commit) on a branch with no issue association; confirm the skill proposes a pre-filled tracking issue, creates it only after confirmation, then links it back to the PR/commit.

**Acceptance Scenarios**:

1. **Given** a PR with no resolvable linked issue, **When** the hook runs, **Then** the developer is offered a pre-filled tracking issue draft derived from the branch/PR context.
2. **Given** the developer confirms creation, **When** the skill proceeds, **Then** a new issue is created, labeled per the canonical registry, and linked back to the PR/commit.
3. **Given** the developer declines (or the run is non-interactive), **When** the hook completes, **Then** no issue is created and a non-blocking warning notes the missing link.

---

### Edge Cases

- **No platform / detached environment**: branch is not connected to GitHub or GitLab (local-only) → skill detects this and exits cleanly with an informational note, taking no action.
- **Wrong platform credentials / insufficient scope**: the token lacks issue-write scope → skill reports the specific missing capability and degrades to advisory output instead of failing.
- **Ambiguous association**: a branch maps to multiple candidate issues with conflicting status → skill reports the ambiguity and asks which issue(s) to act on rather than guessing.
- **Already-correct state**: issue already at the target status and PR already references it → skill is a no-op and says so (idempotent).
- **Closed/locked issue**: linked issue is already closed or locked → skill warns and skips mutation rather than reopening or erroring.
- **Non-interactive context** (CI, automated PR bots): the create-issue prompt cannot be answered → skill defaults to "do not create" and warns.
- **High commit frequency**: rapid successive commits → de-duplication prevents repeated comments/transitions within a branch.
- **Platform rate limiting**: API throttles requests → skill backs off and degrades to a warning without blocking the git action.
- **PR created outside an observed command path** (web UI, or raw `gh pr create`/`glab mr create` typed directly in a terminal not mediated by an AI tool): the PR hook does not observe the creation and does not fire automatically → the developer can run the PR sync manually, and the next commit on the branch still keeps the issue current. This coverage boundary is documented (not a silent guarantee) — see Assumptions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide two distinct, independently invokable skills — one triggered when a pull/merge request is opened, and one triggered when commits land on a feature branch — built on a shared issue-support engine.
- **FR-002**: Each skill MUST run automatically as a hook at its trigger point (PR opened; branch commit) without the developer manually invoking it.
- **FR-003**: The system MUST support both GitHub and GitLab issue trackers, detecting the active platform from the repository rather than requiring per-repo configuration.
- **FR-004**: The system MUST resolve the issue(s) associated with a PR or commit using, in order, the numeric branch-name prefix (e.g., `005-...`), explicit references in the PR/MR description, and references/trailers in commit messages.
- **FR-005**: On a PR trigger, the system MUST post a back-link comment on each linked issue, advance the issue's status label to `needs-review`, and ensure the PR description contains the correct closing keyword for each linked issue.
- **FR-006**: On a commit trigger, the system MUST advance a linked `planned` issue to `in-progress`, and MUST de-duplicate so repeated commits do not re-comment or re-transition the same issue.
- **FR-006a**: Status transitions MUST only move an issue forward in the lifecycle (`planned` → `in-progress` → `needs-review` → `done`); the system MUST NOT regress an issue already at a later stage. These hooks set at most `needs-review`; the `done` label is **not** applied by this feature (see Assumptions — it is owned by the PR-merge/close path, out of scope for v1).
- **FR-007**: All issue mutations MUST be idempotent — re-running a skill against an already-correct issue makes no further changes and reports a no-op.
- **FR-008**: The system MUST be fail-open: any error, missing credential, or unreachable API MUST degrade to a non-blocking warning and MUST NOT abort the developer's PR creation or commit.
- **FR-009**: When no issue can be resolved, the system MUST offer to create a tracking issue pre-filled from available context, and MUST create it only after explicit confirmation; in non-interactive contexts it MUST default to not creating and warn.
- **FR-009a**: Before creating any tracking issue, the system MUST search the tracker for an existing matching open issue (by branch context / title similarity) and reuse it instead of creating a duplicate.
- **FR-009b**: A created tracking issue MUST be best-of-breed — populated from a structured template containing a context summary, acceptance criteria, and bidirectional links to the originating branch/PR/commit — not a bare-title stub.
- **FR-009c**: A created tracking issue MUST be labeled per the canonical registry and immediately linked back to the triggering PR/commit so it enters the same sync lifecycle as a manually authored issue.
- **FR-010**: Status labels and any created issues MUST conform to the project's canonical label registry (e.g., `planned`, `in-progress`, `needs-review`, `done`).
- **FR-011**: The system MUST handle a PR/commit referencing multiple issues by acting on each independently.
- **FR-012**: The system MUST detect and report ambiguous or conflicting issue associations instead of silently choosing one.
- **FR-013**: The system MUST skip mutation on closed or locked issues and warn rather than error.
- **FR-014**: Each skill MUST emit a clear summary of actions taken (or skipped, and why) so the developer can audit hook behavior.
- **FR-015**: The hooks MUST be opt-in/configurable so the automation can be enabled or disabled without removing the skills.
- **FR-016**: Each hook MUST run synchronously within a configurable soft timeout (`hook_timeout_seconds`, default `5`); on timeout it MUST degrade to a warning and let the git action proceed (fail-open). The commit hook exposes `commit_hook_mode` (`sync` | `background`, default `sync`); **v1 implements `sync` only** — `background` is a reserved value for a future release, and if set in v1 the engine MUST fall back to `sync` and emit a one-line warning (never silent, never undefined behavior).
- **FR-017**: Because all mutations are idempotent (FR-007), a timed-out, skipped, or failed run MUST be safely recoverable — re-running the skill (next trigger or manual invocation) brings the issue to the correct state with no duplicate side effects.

### Key Entities *(include if feature involves data)*

- **Issue**: A unit of tracked work on GitHub or GitLab. Key attributes: identifier/number, title, status label, open/closed/locked state, comments, and links to PRs/commits.
- **Pull/Merge Request**: The change-under-review that triggers the PR skill. Key attributes: identifier, title, description (containing references and closing keywords), source branch, and linked issues.
- **Commit**: A change recorded on a feature branch that triggers the commit skill. Key attributes: subject/message (may contain references/trailers), branch, and derived issue association.
- **Branch**: The working line of development; its name (notably a numeric prefix) is a primary signal for issue association.
- **Issue-Support Action**: A single change the engine applies — comment, status-label transition, closing-keyword insertion, or issue creation — with a result of applied / skipped / failed and a reason.
- **Hook Trigger**: The event binding (PR-opened, branch-commit) that fires a skill, including whether the context is interactive.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a PR is opened on a branch with a resolvable issue, the linked issue reflects the correct back-link and status within one hook run, with no manual issue edits required in at least 95% of cases.
- **SC-002**: 100% of hook runs leave the underlying git action (PR creation, commit) successful even when the issue tracker is unreachable (zero blocking failures).
- **SC-003**: Across a series of 10 consecutive commits on one branch, the linked issue is transitioned and/or commented at most once for that lifecycle stage (idempotent / de-duplicated).
- **SC-004**: A developer can determine exactly what each hook did (or skipped, and why) from the skill's summary output without inspecting the issue tracker manually.
- **SC-005**: Manual issue-status upkeep (moving issues to in-progress / needs-review by hand) is eliminated for branches that follow the project's naming and reference conventions.
- **SC-006**: Both skills operate against GitHub and GitLab repositories with no per-repository configuration beyond enabling the hook.
- **SC-007**: A hook adds no more than the configured timeout (default 5s) to any git action, and after the first commit on a branch, subsequent commits add no perceptible delay (sub-second no-op via de-duplication).
- **SC-008**: An auto-created tracking issue contains a context summary, acceptance criteria, canonical labels, and a working link to its PR/commit in 100% of cases, and no duplicate issue is created when a matching one already exists.

## Assumptions

- **Platform detection reuse**: The active platform (GitHub vs GitLab vs plain git) is detected from the repository using the project's existing platform-detection approach; no new per-repo platform setting is introduced.
- **Issue association conventions**: The primary association signal is the numeric branch-name prefix already used in this project (e.g., `005-issue-linking-hooks`), supplemented by explicit references in PR descriptions and commit messages.
- **Label vocabulary**: Status transitions use the project's canonical label set (`planned`, `in-progress`, `needs-review`, `done`, plus `follow-up`/`future`) as the source of truth.
- **"PR is executed" interpretation**: Interpreted as a PR/MR being **opened/created** (the primary trigger). Re-runs on subsequent updates are out of scope for v1 and may be added later.
- **Commit trigger granularity**: The commit skill targets feature-branch commits; the exact hook surface (e.g., post-commit vs pre-push) is a design-phase decision, constrained by the fail-open, de-duplication, and bounded-timeout requirements. Execution mode is configurable (`commit_hook_mode`, default `sync`) per the Clarifications.
- **Credentials**: The environment provides a platform token with issue read/write scope; insufficient scope degrades to advisory behavior rather than failure (consistent with the known limitation that some tokens lack project scope).
- **Authoring location**: The two skills live alongside existing issue/PR skills in the project's skill source of truth and reuse existing platform-agnostic git/issue operations rather than introducing a new integration layer.
- **`done` label ownership**: This feature advances issues only as far as `needs-review`. The `done` label belongs to the PR-merge/close path (handled by merge automation, CI, or a human, e.g. via existing triage skills) and is **out of scope for v1**. The lifecycle in FR-006a shows `done` for completeness, not as a transition these hooks perform; consequently a `Closes #N` that closes an issue on merge without a `done` label is acceptable and not a conformance violation of FR-010.
- **PR-trigger coverage boundary**: "Automatically when a PR is opened" (FR-002) is delivered for PR/MR creation that flows through an AI-tool-mediated command or `git_ops.sh pr-create` (observed by the unified PostToolUse hook). PR creation via the platform web UI, or raw `gh`/`glab` typed directly outside a tool, is **not** auto-covered in v1 — there is no native git "PR-opened" event to hook. This is documented rather than silently assumed; a server-side trigger (GitHub Actions / GitLab CI `pull_request: opened`) is the noted future complement for universal coverage.
- **Default-off safety**: Hooks ship opt-in so adopting repositories explicitly enable the automation.
