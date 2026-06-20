# Feature Specification: Autonomous PR Lifecycle & Merge Loop

**Feature Branch**: `361-auto-dev-merge-loop`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: "Update our auto-dev to perform the following: Add to our existing loop. After PR is complete. Monitor it for comments, pipeline failures. run the appropriate command to address. `/address-pr-comments` and `/pr-review` and `/verify` if all these clear after 2-3 revisions Merge to main.. Additionally, ensure that is only waits 10 minutes per run. If there's no work after 5 loop attempts with no work stop running the loop. Ensure that it iterates, and validates EVERY tasks 1 by 1. Where applicable use parallel reviews etc."

## Overview

Today `auto-issue-dev` develops **one** opted-in issue per invocation and stops at
PR-open — its Critical Rule #1 is *"Never merge; a human reviews and merges."*
This feature extends the autonomous loop **past** PR-open: after a PR is opened, the
loop monitors it for review comments and pipeline failures, remediates them by running
the existing `/address-pr-comments`, `/pr-review`, and `/verify` skills across a bounded
number of revision cycles, and — when every signal is clear — **merges the PR to main**.
It also adds loop-lifecycle controls: self-paced advancement (proceed the moment state is
actionable, so the loop moves as fast as external state allows) with a hard per-run time
ceiling as a backstop, and a self-termination rule when no work remains.

This **deliberately supersedes** the current "never merge" invariant for
automation-authored PRs that pass all gates. Because `main`'s branch protection requires
a code-owner review that the automation's own account cannot self-supply, the verified
merge uses **admin privileges to bypass branch protection**. With human review removed
from the happy path, the deterministic checks (`/verify`, CI) and the semantic checks
(`/pr-review`, the #360 verification gate) become the **only** safety controls — so
fail-closed behavior is mandatory throughout.

## Clarifications

### Session 2026-06-20

- Q: How should the loop reconcile "process items 1-by-1" with async CI and "move as fast as it can"? → A: **Interleave monitoring, serialize merges** — monitor/advance multiple managed PRs (and develop a new issue) concurrently, but perform at most one merge-to-main at a time; the serialization applies only to the irreversible merge step, and every item is still validated independently.
- Q: Which review comments should block the merge? → A: **Actionable/unresolved only** — a human "request changes" review or an unresolved actionable thread blocks; informational/nit bot comments are resolved by `/address-pr-comments` but do not hard-block an otherwise-clear PR.
- Q: If the only outstanding item is a managed PR still pending CI, does that run count toward the 5-empty-run stop? → A: **No — in-flight counts as work**; the empty counter advances only when there are zero issues to develop AND zero managed PRs in any active state.
- Q: If main's CI goes red right after the loop merges a PR, what should it do? → A: **Halt + flag for human** — stop merging further PRs, record the offending PR, and do NOT attempt an automated revert.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Remediate PR feedback automatically (Priority: P1)

After the loop opens (or finds) an eligible automation PR, it watches that PR for
unresolved review comments (human or bot) and pipeline/CI failures. When it finds any, it
runs the appropriate remediation skill — `/address-pr-comments` for comments, `/verify`
for local correctness, `/pr-review` for mergeability — fixes the issues, pushes, and
re-checks. It repeats this up to a bounded number of revision cycles per PR.

**Why this priority**: This is the foundational slice — keeping automation PRs green and
comment-free is valuable on its own, even if a human still performs the final merge. It is
also the precondition for any safe auto-merge.

**Independent Test**: Open a PR with a deliberately failing check and a review comment;
run the loop; confirm it runs `/address-pr-comments` and `/verify`, pushes a fix, and the
PR reaches a clean state (or is handed to a human after the revision budget) — without
merging.

**Acceptance Scenarios**:

1. **Given** an automation PR with a failing pipeline, **When** the loop processes it,
   **Then** it runs `/verify`, applies and pushes a fix, and re-evaluates the pipeline.
2. **Given** an automation PR with unresolved review comments, **When** the loop processes
   it, **Then** it runs `/address-pr-comments` to fix/reply/resolve each item and pushes
   the changes.
3. **Given** a PR still not clear after the revision budget (default 3), **When** the
   budget is exhausted, **Then** the loop stops revising it, labels it for human attention
   with a reason, does NOT merge it, and proceeds to the next work item.

---

### User Story 2 - Verified auto-merge to main (Priority: P1)

When a managed PR is fully clear — pipeline green, no unresolved actionable review comments,
`/pr-review` disposition is "merge", `/verify` passes with no blocking failures, and the
verification gate (Tier-1) passes — the loop merges it to main. Because the automation
account cannot satisfy the required code-owner review, the loop uses admin privileges to
bypass branch protection for the merge. If it cannot merge safely (no admin authority, an
unresolvable conflict, or any blocking signal), it hands the PR to a human instead of
forcing the merge.

**Why this priority**: This is the headline capability the user asked for ("Merge to
main") and the point of the feature: closing the loop end-to-end without a human in the
happy path.

**Independent Test**: Present a PR that satisfies every clear condition; run the loop;
confirm it merges to main and prunes the branch. Then present a PR with one blocking
condition (e.g. a failing check); confirm it is NOT merged and is handed to a human.

**Acceptance Scenarios**:

1. **Given** a managed PR meeting all clear conditions, **When** the loop evaluates it,
   **Then** it merges the PR to main (bypassing branch protection with admin rights) and
   removes the merged branch.
2. **Given** a managed PR with a failing pipeline, an unresolved human "request changes"
   review, or a blocking verification-gate finding, **When** the loop evaluates it,
   **Then** it does NOT merge under any revision count and routes the PR to a human.
3. **Given** the merging actor lacks admin authority to bypass protection, **When** a PR
   is otherwise clear, **Then** the loop does NOT partially merge; it labels the PR
   "ready-to-merge" for a human and records the reason.
4. **Given** the PR has a merge conflict with main, **When** the loop attempts the merge,
   **Then** it attempts one automated update from main and, if still conflicted, hands the
   PR to a human rather than forcing a conflicted merge.

---

### User Story 3 - Fast, bounded, self-terminating loop (Priority: P2)

The loop runs unattended and must move **as fast as external state allows** without running
forever or hanging. Rather than waiting a fixed interval, each run is **self-paced**: it
proceeds the moment a PR's state becomes actionable (CI concludes, comments settle, or a
blocking signal appears), polling on a cadence matched to how quickly that state changes. A
hard per-run **ceiling** (default 10 minutes, configurable) bounds how long any single run
will wait on external state — a backstop against a stuck pipeline, not a target to wait
out. The loop counts consecutive runs that find no work; after 5 such empty runs in a row
it stops entirely. The loop MAY monitor and advance several managed PRs (and develop a new
issue) concurrently, but it serializes the one irreversible step — at most one merge-to-main
happens at a time — and validates every item independently. Independent reviews within a
single item may also run in parallel to save wall-clock time.

**Why this priority**: Throughput plus operational safety. Self-pacing keeps the loop fast
(no idle waiting when CI is already done); the ceiling and empty-run stop prevent it from
blocking indefinitely on a stuck pipeline or spinning forever on an empty queue.

**Independent Test**: Point the loop at a PR whose CI finishes quickly and confirm it acts
within seconds of completion (not after a fixed delay). Separately, point it at a PR whose
CI never finishes and confirm a single run ends at the ~10-minute ceiling and re-evaluates
on the next run. Finally, run against an empty queue and confirm it stops after exactly 5
empty runs.

**Acceptance Scenarios**:

1. **Given** a run watching a pipeline, **When** the pipeline concludes (pass or fail),
   **Then** the run acts on the result immediately rather than waiting any fixed interval.
2. **Given** a run waiting on a pipeline that does not complete, **When** the per-run
   ceiling (default 10 minutes) is reached, **Then** the run ends and the PR is
   re-evaluated on a later run (no indefinite blocking).
3. **Given** 5 consecutive runs that find no eligible work, **When** the 5th empty run
   completes, **Then** the loop stops and reports that it terminated on the empty-work
   condition.
4. **Given** a run that performs any work (develops an issue, addresses a PR, or merges),
   **When** the run completes, **Then** the consecutive-empty-run counter resets to zero.
5. **Given** multiple eligible work items, **When** the loop runs, **Then** it performs at
   most one merge-to-main at a time (no concurrent or batch merges), even though it may
   monitor other managed PRs and run reviews concurrently.
6. **Given** a run whose only outstanding item is a managed PR still pending CI, **When**
   the run completes without merging, **Then** the consecutive-empty-run counter does NOT
   advance (the in-flight PR counts as work).

---

### Edge Cases

- **New feedback mid-cycle**: a fresh comment or check failure arrives after a revision —
  counts against the same PR's revision budget; the PR is re-evaluated, not merged early.
- **Revision budget exhausted**: PR still not clear after the max cycles → labeled for
  human, reason recorded, not merged, loop moves on.
- **CI concludes early**: the run acts immediately on the result — it does not wait out the
  ceiling.
- **CI still running at the per-run ceiling**: the run ends; the PR is neither merged nor
  failed — it is simply re-checked on a later run.
- **Non-actionable bot nit**: an informational/nitpick bot comment that `/address-pr-comments`
  classifies as non-actionable is acknowledged/resolved but does NOT hard-block an otherwise-clear
  PR — only human "request changes" and unresolved actionable threads block.
- **Post-merge main breakage**: a PR passes branch CI but main's CI goes red after the merge —
  the loop halts (stops merging further PRs), records the offending PR, flags for a human, and
  does NOT attempt an automated revert.
- **Only in-flight work remains**: a run that finds only managed PRs still pending CI or
  mid-revision does not increment the empty-run counter; the loop keeps watching rather than
  counting toward its stop condition.
- **Human "request changes" review present**: treated as a hard block — never auto-merged,
  regardless of other green signals, until the human resolves it.
- **Explicit hold**: a designated "do-not-auto-merge" / hold label on a PR forces the
  human path.
- **Verification gate / `/pr-review` says don't merge**: respected as a hard block.
- **Human-authored PR encountered**: out of scope — skipped, not counted as actionable
  work.
- **Conflict with main**: one automated update attempt; if unresolved, hand to human.
- **Concurrent loop invocations**: a concurrency guard prevents two runs from acting on
  the same PR simultaneously.
- **Merge succeeds but branch cleanup fails**: the merge is still recorded as successful;
  branch cleanup failure is logged, never reverts the merge.

## Requirements *(mandatory)*

### Functional Requirements

**Monitoring & remediation**

- **FR-001**: The loop MUST, after a managed PR is open, detect (a) unresolved review
  comments (human or bot) and (b) pipeline/CI failures on that PR.
- **FR-002**: When unresolved comments exist, the loop MUST run `/address-pr-comments` to
  triage, fix, re-test, push, and reply-to or resolve each item.
- **FR-003**: The loop MUST run `/verify` to validate correctness; test and security
  failures are blocking, lint warnings are non-blocking (consistent with existing
  `auto-issue-dev` behavior).
- **FR-004**: The loop MUST run `/pr-review` and obtain a "merge" disposition before
  considering a PR mergeable.
- **FR-005**: The loop MUST attempt remediation across at most a configurable number of
  revision cycles per PR (default **3**, per the user's "2-3 revisions").
- **FR-006**: If a PR is not clear after the revision budget, the loop MUST NOT merge it,
  MUST mark it for human attention with a reason, and MUST proceed to the next work item.

**Verified merge**

- **FR-007**: The loop MUST merge a PR to main ONLY when ALL of the following hold
  simultaneously: pipeline/CI green, no unresolved **actionable** review comments (see
  FR-007a), `/pr-review` disposition = merge, `/verify` passes with no blocking failure, and
  the verification gate Tier-1 passes.
- **FR-007a**: For the comment gate, the loop MUST treat a human "request changes" review
  and any unresolved actionable review thread as blocking; informational or nitpick bot
  comments that `/address-pr-comments` classifies as non-actionable MUST be acknowledged or
  resolved but MUST NOT hard-block an otherwise-clear PR.
- **FR-008**: When the merge is otherwise authorized but branch protection blocks it
  because the automation account cannot self-approve, the loop MUST use admin privileges to
  bypass the review-required protection to complete the merge.
- **FR-009**: If admin bypass is unavailable (actor lacks admin), the loop MUST fail
  closed: leave the PR open, mark it "ready-to-merge" for a human, and never perform a
  partial or forced merge.
- **FR-010**: On a merge conflict with main, the loop MUST attempt exactly one automated
  update from main; if the conflict persists, it MUST hand the PR to a human and MUST NOT
  force a conflicted merge.
- **FR-011**: On a successful merge, the loop MUST prune the merged source branch.
- **FR-012**: The loop MUST NOT merge while a human "request changes" review or a
  designated hold label is present, regardless of any green signals or remaining revision
  budget.
- **FR-012a**: After a successful merge, the loop MUST verify main's post-merge CI health.
  If main's CI fails following the merge, the loop MUST halt (stop merging any further PRs),
  record the offending PR, and flag it for a human. The loop MUST NOT attempt an automated
  revert.

**Scope & ordering**

- **FR-013**: The loop MUST act only on PRs authored by the automation set (auto-dev plus
  recognized bots, e.g. Forge, Palette, Jules, Bolt, Copilot). It MUST skip
  human-authored PRs.
- **FR-014**: The loop MAY monitor and advance multiple managed PRs (and develop a new
  issue) concurrently, but it MUST serialize the merge step — at most one merge-to-main in
  flight at a time, never batch or concurrent merges. Each work item MUST be validated
  independently; the serialization constraint applies only to the irreversible merge, not to
  monitoring or waiting.
- **FR-015**: The loop SHOULD run independent reviews within a single work item in parallel
  (e.g. parallel-agent verification, concurrent per-comment analysis) to reduce wall-clock
  time, without weakening the one-merge-at-a-time ordering in FR-014.
- **FR-016**: The new monitoring/merge responsibilities MUST extend, not replace, the
  existing develop→PR flow; the loop continues to develop at most one new issue per run.

**Loop lifecycle**

- **FR-017**: Each loop run MUST be **self-paced** — it MUST proceed as soon as a PR's
  state is actionable (CI concluded, comments settled, or a blocking signal appeared)
  rather than waiting a fixed interval, polling on a cadence matched to how quickly the
  watched state changes, so the loop advances as fast as external state allows.
- **FR-017a**: A configurable hard per-run **ceiling** (default **10 minutes**) MUST bound
  the total time a single run will wait on external state; on reaching the ceiling the run
  MUST end and the affected PR MUST be re-evaluated on a later run. The ceiling is a
  backstop, never a minimum wait.
- **FR-018**: The loop MUST track consecutive runs that find no eligible work and MUST stop
  entirely after **5** consecutive empty runs.
- **FR-018a**: A run counts as "empty" ONLY when there are zero issues to develop AND zero
  managed PRs in any active state (pending CI, awaiting revision, or mid-remediation). A run
  that finds an in-flight managed PR MUST NOT increment the empty counter, even if it took no
  mutating action — in-flight work counts as work.
- **FR-019**: Any run that performs work (develops an issue, addresses a PR, or merges)
  MUST reset the consecutive-empty-run counter to zero.

**Safety, audit & hygiene**

- **FR-020**: The loop MUST treat every infrastructure failure of a safety control
  (reviewer/gate cannot run, CI status unobtainable, merge API error) as fail-closed — it
  MUST NOT merge on an indeterminate signal.
- **FR-021**: The loop MUST record every revision, merge, and human hand-off in the audit
  log, extending the existing `auto-issue-dev` audit record.
- **FR-022**: All content sent to reviewers, posted as PR annotations, or written to logs
  MUST be redacted of secrets, reusing the existing redaction path.
- **FR-023**: A concurrency guard MUST prevent two loop runs from acting on the same PR at
  the same time.

### Key Entities

- **Work item**: a unit the loop processes to completion — either a new issue to develop or
  an open managed PR to monitor/merge.
- **Managed PR**: an open PR authored by the automation set and therefore eligible for the
  monitor-and-merge flow; carries a lifecycle state (monitoring → addressing → verified →
  merged | needs-human).
- **Revision cycle**: one address→verify→review pass against a single PR; bounded by the
  revision budget.
- **Clear conditions**: the complete set of signals (CI green, no unresolved *actionable*
  comments, `/pr-review` = merge, `/verify` pass, verification gate Tier-1 pass, no human
  block) that must all hold for a merge.
- **Actionable comment**: a review comment requiring a code or behavioral change — a human
  "request changes" or an unresolved actionable thread. Informational/nit bot comments are
  non-actionable and do not gate the merge.
- **Loop run / empty-run counter**: one invocation of the loop and the consecutive count of
  runs that found no eligible work.
- **Audit record**: the extended log entry capturing per-item outcome, revisions, merge
  result, and hand-off reason.
- **Automation author allowlist**: the set of PR authors (auto-dev + named bots) the loop
  is permitted to act on.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For managed PRs whose comments/pipeline failures are addressable, the loop
  brings the PR to a merged or cleanly-handed-off state without human intervention in at
  least 80% of cases within the revision budget.
- **SC-002**: Zero PRs are ever merged to main while a pipeline is failing, a human
  "request changes" review or an unresolved actionable comment thread exists, a hold label
  is present, or a blocking verification finding exists (hard invariant — 0 violations).
- **SC-003**: No single loop run blocks longer than the configured ceiling (default 10
  minutes) waiting on external state, and in the common case a run advances within seconds
  of the watched state becoming actionable — it never waits out a fixed interval.
- **SC-004**: The loop terminates on its own after no more than 5 consecutive empty runs —
  it never runs indefinitely against an empty queue.
- **SC-005**: At most one merge-to-main is ever in flight at a time — no concurrent or batch
  merges are ever performed (even while multiple PRs are monitored concurrently).
- **SC-006**: 100% of merges and human hand-offs are captured in the audit log with a
  reason.
- **SC-007**: When the loop lacks merge authority or cannot auto-resolve a conflict, it
  hands the PR to a human with a clear reason 100% of the time — it never performs a
  partial or forced merge (fail-closed).
- **SC-008**: A reviewer or gate infrastructure failure never results in a merge (0
  merges on indeterminate safety signals).
- **SC-009**: After a merge that turns main's CI red, the loop performs zero further merges
  until a human clears the breakage (no merges are ever stacked onto a known-broken main).

## Assumptions

- **"2-3 revisions"** is interpreted as a configurable maximum of **3** revision cycles per
  PR before handing off to a human.
- **"Merge to main"** is interpreted as an actual merge performed by the loop, using admin
  privileges to bypass `main`'s review-required branch protection when no human approval is
  available (per the merge-authority decision). This intentionally supersedes the existing
  "never merge" rule for automation PRs that pass all gates.
- **Merge method** defaults to squash (matching the repo's existing `(#NNN)` squash-merge
  history) with deletion of the merged source branch; this is a documented default, not a
  clarified decision, and can be revisited in planning.
- **Post-merge health** is judged by main's CI status as reported by the platform after the
  merge commit lands (reusing existing status checks); no new health signal is introduced.
- **Scope** is automation-authored PRs (auto-dev plus recognized bots); human-authored PRs
  are skipped (per the PR-scope decision).
- The loop **orchestrates existing skills** (`/address-pr-comments`, `/pr-review`,
  `/verify`) and the **#360 verification gate** rather than reimplementing their logic;
  this feature depends on the #360 verification gate being present, since the merge
  decision consumes its Tier-1 verdict.
- The loop runs via the existing `/loop /auto-issue-dev` harness; self-paced advancement,
  the 10-minute per-run ceiling (backstop), and the 5-empty-run stop are new controls
  layered onto that harness. Self-pacing was chosen over a fixed 10-minute wait per the
  goal of moving as fast as external state allows; 10 minutes is the ceiling, not the
  cadence.
- Branch-protection configuration is as currently observed on `main`: review-from-code-owners
  required, admin enforcement disabled (admin can bypass), required signatures disabled.
- The platform is GitHub (`gh`) as the primary target, with GitLab parity provided through
  the existing `git_ops.sh` abstraction where available.
- "Pipeline failures" refers to the PR's CI status checks as reported by the platform; a
  pipeline that is still running is "pending", not "failing".
- The existing audit log and secret-redaction utilities are reused unchanged.

## Dependencies

- **#360 verification gate** (`docs/superpowers/specs/2026-06-18-auto-issue-dev-verification-gate-design.md`):
  the Tier-1 verdict is a precondition for the verified merge.
- Existing skills: `/address-pr-comments`, `/pr-review`, `/verify`.
- Existing scripts: `auto_issue_dev.sh`, `git_ops.sh`, `audit_log.sh`, `git_platform.sh`.
- The `/loop` harness that re-invokes `auto-issue-dev` with fresh context.
