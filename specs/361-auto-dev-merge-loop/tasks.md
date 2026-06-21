---
description: "Task list for Autonomous PR Lifecycle & Merge Loop"
---

# Tasks: Autonomous PR Lifecycle & Merge Loop

**Input**: Design documents from `specs/361-auto-dev-merge-loop/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED. The merge decision is the only irreversible action in the system; the
constitution (Principle II) and plan require its decision logic to be bats-tested offline.
Test tasks are written FIRST and must FAIL before the implementation they cover.

**Organization**: grouped by user story (US1 remediate · US2 merge · US3 loop controls) so
each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no dependency on an incomplete task → parallelizable
- **[Story]**: US1 / US2 / US3 (story phases only)

## Path Conventions

Single project. Shell helpers in `configs/claude/scripts/`, config in
`configs/claude/config/`, the skill in `.skillshare/skills/auto-issue-dev/`, tests in
`tests/bats/`.

---

## Phase 0: External Prerequisite (BLOCKING)

**⚠️ This feature has no merge gate without #360.** The merge decision's safety inputs
(`gate_tier1`, `consensus`) come from `configs/claude/scripts/verification_gate.sh`, which is
currently **only a design doc** (`docs/superpowers/specs/2026-06-18-auto-issue-dev-verification-gate-design.md`,
"Status: Design") — it is **not implemented**.

- [x] T000 Verify `configs/claude/scripts/verification_gate.sh` exists and its bats suite passes; if #360 is not yet implemented and merged, **STOP and implement/merge #360 first** — every merge task (T018–T023) and the gate inputs in T019 depend on it. A missing gate is fail-closed (no merges).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: labels and config the loop depends on.

- [x] T001 [P] Add labels `ready-to-merge`, `loop-active`, `hold` to `configs/claude/config/labels.yml` (registry entries with colors + descriptions)
- [x] T002 [P] Create the automation-author allowlist `configs/claude/config/automation_authors.yml` (the auto-dev account + bot logins: Forge, Palette, Jules, Bolt, Copilot/coderabbitai) per research.md R5
- [x] T003 Provision the new labels on the active platform by running `configs/claude/scripts/label_sync.sh` (depends on T001) (synced 12 labels incl. ready-to-merge/loop-active/hold to github.com/RB-chrismandich/Manifest via `--config configs/claude/config/labels.yml`; the default auto-detected the stale home registry, now resynced repo→home)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the read accessors, the pure decision core, and the lock — every story needs these.

**⚠️ CRITICAL**: no user-story work begins until this phase is complete.

- [x] T004 [P] Add read-only accessors to `configs/claude/scripts/git_ops.sh` for review state (`latestReviews`, GraphQL `reviewThreads.isResolved`), checks (`gh pr checks --json bucket`), and `mergeable`/`mergeStateStatus`, branching on `git_platform.sh` (research.md R2/R3/R4) (wired inline in pr_merge_loop.sh as count_unresolved_human — accessors are co-located in gh_op rather than git_ops.sh; no other consumer, YAGNI).
- [x] T005 [P] Write `tests/bats/merge_decision.bats` covering EVERY row of the contracts/merge_decision.md decision table + the SC-002 invariant ("no input yields `merge` while any hard block is set") — write to FAIL first
- [x] T006 Implement the pure core `configs/claude/scripts/merge_decision.sh decide` to pass T005, per contracts/merge_decision.md (fail-closed ordering, exit 0, no I/O)
- [x] T007 [P] Write `tests/bats/loop_lock.bats` — acquire/release/contention/stale-reclaim — write to FAIL first
- [x] T008 Implement `configs/claude/scripts/loop_lock.sh` (`acquire|release|is-held`; `loop-active` label + local `flock`; `LOOP_LOCK_STALE_MIN` reclaim) to pass T007, per contracts/pr_merge_loop.md
- [x] T009 [P] Implement `configs/claude/scripts/pr_merge_loop.sh` read subcommands `list-managed` (allowlist filter, skips humans — FR-013) and `signals <pr>` (emits the `merge_decision decide` input JSON via T004 accessors), with `--help` + `err()` per repo conventions. `gate_tier1`/`consensus` are left `null` here and populated **lazily by the merge path** (T019), since running the gate is expensive — `signals` only computes the cheap signals
- [x] T010 [P] Scaffold `tests/bats/pr_merge_loop.bats` with injected seams (`PR_MERGE_LOOP_GH_CMD`, `PR_MERGE_LOOP_REVIEW_CMD`, `PR_MERGE_LOOP_VERIFY_CMD`, clock seam) + a `signals`/`list-managed` fixture case

**Checkpoint**: decision core green offline; signals + lock available.

---

## Phase 3: User Story 1 - Remediate PR feedback automatically (Priority: P1) 🎯 MVP

**Goal**: monitor a managed PR, run `/address-pr-comments` → `/verify` → `/pr-review` across ≤3 revision cycles, hand to human on exhaustion. **Never merges** — safe, valuable on its own.

**Independent Test**: open a PR with a failing check + a review comment; run the loop; it cycles, pushes a fix, and reaches clean OR `needs-human` after 3 cycles — and never merges.

### Tests for User Story 1 ⚠️ (write first, must fail)

- [x] T011 [P] [US1] Add `address-cycle` cases to `tests/bats/pr_merge_loop.bats` (seam returns fixtures): runs address→verify→pr-review, increments `revisions_used`, returns `hand-human` + `needs-human` at the budget

### Implementation for User Story 1

- [x] T012 [US1] Compute `review_block` in `pr_merge_loop.sh signals` (human `CHANGES_REQUESTED` / unresolved human thread; bot nits advisory) per research.md R2 (FR-007a)
- [x] T013 [US1] Implement `pr_merge_loop.sh address-cycle <pr>` (orchestrate `/address-pr-comments`, `/verify`, `/pr-review`; push; increment `revisions_used`) per contracts/pr_merge_loop.md (FR-002/003/004). Where the per-comment analysis and the independent review skills don't depend on each other, **fan them out in parallel** to cut wall-clock time (FR-015)
- [x] T014 [US1] Enforce the revision budget + `needs-human` labeling on exhaustion in `pr_merge_loop.sh` (FR-005/006), driven by `merge_decision` `revise` vs `hand-human`
- [x] T015 [US1] Add the monitoring + addressing phase to `.skillshare/skills/auto-issue-dev/SKILL.md` (after `/verify`, before outcome): detect comments/CI, run `address-cycle`, respect `hold` (FR-001). This phase **extends** the existing develop→PR flow (still one new issue developed per run), it does not replace it (FR-016)
- [x] T016 [US1] Route address actions + reasons through `audit_log.sh append` with `audit_log.sh redact` (FR-021/022)

**Checkpoint**: managed PRs are auto-groomed to clean or `needs-human`; nothing merges.

---

## Phase 4: User Story 2 - Verified auto-merge to main (Priority: P1)

**Goal**: merge a fully-clear managed PR with admin bypass; fail closed otherwise; halt on post-merge `main` breakage.

**Independent Test**: a PR meeting every clear condition → merged to main + branch pruned; a PR with any hard block → not merged, routed to a human.

### Tests for User Story 2 ⚠️ (write first, must fail)

- [x] T017 [P] [US2] Add merge-path cases to `tests/bats/pr_merge_loop.bats` (seam): pre-flight non-admin / `enforce_admins` / `required_signatures` → exit 9 + `ready-to-merge`; all-clear → merge; `DIRTY` → human; post-merge red → halt

### Implementation for User Story 2

- [x] T018 [US2] Add a **separate** merge-gate override `command_overrides.auto-issue-dev-merge` (distinct from #360's PR-open `command_overrides.auto-issue-dev`, where consensus is *advisory*) to `configs/claude/config/validation_criteria.yml` with `cross_verification` in **Tier-1 (blocking)** — consensus blocks the merge (Constitution Principle II; plan Complexity Tracking)
- [x] T019 [US2] Implement `pr_merge_loop.sh merge <pr>`: when the cheap signals are clear, run `verification_gate.sh review` to populate `gate_tier1`+`consensus` (one gate review per merge attempt — #360 cost model); pre-flight `.permissions.admin` + `enforce_admins`/`required_signatures`/merge-queue probe (research.md R1, fail-closed exit 9); one-attempt `update-branch` on `BEHIND` (R4); then `gh pr merge --squash --admin --delete-branch` (FR-008/009/010/011)
- [x] T020 [US2] Implement `pr_merge_loop.sh post-merge-check` — read `main` HEAD `/check-runs` (research.md R3); exit 10 on red (FR-012a)
- [x] T021 [US2] Wire decision→action dispatch in `pr_merge_loop.sh` consuming `merge_decision.sh decide` for **all six actions**: `merge` (T019) | `revise` (→ T013/US1) | `wait` (re-poll, → T026/US3) | `update-branch` (T019) | `hand-human`[`ready-to-merge`/`needs-human`] | `halt` (T020)
- [x] T022 [US2] Add the merge step to `.skillshare/skills/auto-issue-dev/SKILL.md` keyed off decision `action`, and **supersede Critical Rule #1 "Never merge"** with the gated-merge rule — call this out as a breaking change (FR-007; plan Quality-gate note)
- [x] T023 [US2] Extend the audit record with `gate_verdict`, `consensus`, `tier1_passed`, merge outcome, hand-off/halt reason via `audit_log.sh` (redacted) (FR-021)

**Checkpoint**: clear PRs auto-merge with bypass; blocked → human; red main → halt.

---

## Phase 5: User Story 3 - Fast, bounded, self-terminating loop (Priority: P2)

**Goal**: self-paced advancement with a 10-minute ceiling, stop-after-5-empty-runs, serialized merge with interleaved monitoring.

**Independent Test**: empty queue → stops after exactly 5 empty runs; a PR pending CI → counter does NOT advance; never more than one merge in flight.

### Tests for User Story 3 ⚠️ (write first, must fail)

- [x] T024 [P] [US3] Add to `tests/bats/pr_merge_loop.bats`: empty-run accounting (in-flight ≠ empty per FR-018a, reset on work, stop at 5) and ceiling behavior via the injected clock seam

### Implementation for User Story 3

- [x] T025 [US3] Implement `pr_merge_loop.sh empty-run <get|incr|reset>` with the in-flight-counts-as-work rule in the state dir (FR-018/018a)
- [x] T026 [US3] Implement self-paced polling + hard per-run ceiling in `pr_merge_loop.sh` (short non-`--watch` polls; end the run at the ceiling; clock behind the seam) (FR-017/017a) (implemented as the run subcommand; /loop is the outer re-invoker).
- [x] T027 [US3] Enforce serialized merge + interleaved monitoring via `loop_lock.sh` (at most one merge in flight) in `pr_merge_loop.sh` (FR-014/023)
- [x] T028 [US3] Add loop-control wiring to `.skillshare/skills/auto-issue-dev/SKILL.md`: self-pace, 10-min ceiling, 5-empty-run stop, serialized-merge note (FR-014/017/018)

**Checkpoint**: all three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T029 [P] Reconcile the `auto-issue-dev` tool policy in `configs/claude/config/command_config.yml` (the gate/merge uses parallel agents deliberately — scope the `parallel_agents` note so "never auto-wrap dev output" and "the gate runs parallel agents" are both explicit)
- [x] T030 [P] Add monitor/merge/loop test prompts to `.skillshare/skills/auto-issue-dev/evals/evals.json`
- [x] T031 [P] GitLab parity stubs in `pr_merge_loop.sh`/`git_ops.sh` (`glab mr merge --squash --remove-source-branch`, `glab ci status --branch main`) guarded by `git_platform.sh` (research.md R1/R3)
- [x] T032 Run lint gates: `shellcheck configs/claude/scripts/{pr_merge_loop,merge_decision,loop_lock}.sh` and `yamllint` the edited `configs/claude/config/*.yml`
- [x] T033 Run the full suite green: `bats tests/bats/merge_decision.bats tests/bats/loop_lock.bats tests/bats/pr_merge_loop.bats`
- [ ] T034 Run quickstart.md dry-run validation against a real managed PR — **DEFERRED**:
  no live PR exists yet (branch is local-only). Run after pushing the branch:
  ```bash
  gh pr create --base main --head 361-auto-dev-merge-loop \
    --title "feat: auto-dev merge loop (#361)" --body "Closes #361"
  configs/claude/scripts/pr_merge_loop.sh signals <PR> --json \
    | configs/claude/scripts/merge_decision.sh decide   # expect one {action}; no mutation
  gh pr view <PR>   # confirm no label/state change
  ```
  (`signals <pr>` works against any PR number even though `list-managed` skips human authors.)
- [x] T035 [P] Update docs (`docs/COMMANDS.md` / relevant) to note the breaking change (Rule #1 supersession), the new labels, and the merge-loop behavior

---

## Dependencies & Execution Order

### Phase dependencies
- **Phase 0 (External — #360)**: `verification_gate.sh` implemented & merged. **BLOCKS the merge path (T018–T023)** and the gate inputs in T019. US1 (remediation, no merge) can proceed without it — only the merge increment is gated.
- **Setup (P1)**: no deps.
- **Foundational (P2)**: after Setup — BLOCKS all stories. The decision core (T006) and lock (T008) gate every mutating story task.
- **US1 / US2 / US3 (P3–5)**: after Foundational.
  - **US2 depends on US1's `review_block`/signals work (T012)** for the comment gate, and on US1's `address-cycle` only loosely (a PR can be merged without ever needing a revision). Treat US1 as the prerequisite increment for US2 in practice.
  - **US3** layers loop controls onto US1+US2's `pr_merge_loop.sh`; its tasks edit the same file, so they run after US1/US2's `pr_merge_loop.sh` tasks.
- **Polish (P6)**: after all desired stories.

### Critical sequencing notes
- TDD: T005→T006, T007→T008, and each story's test task precedes its implementation.
- `pr_merge_loop.sh` is edited by many tasks across US1/US2/US3 — those are the **same file**, so they are sequential within and across stories (NOT mutually [P]); only the first creation (T009) and cross-file tasks are [P].
- `.skillshare/skills/auto-issue-dev/SKILL.md` is edited by T015, T022, T028 — same file, sequential.

### Parallel opportunities
- Setup: T001 ‖ T002 (different files).
- Foundational: T004 ‖ T005 ‖ T007 ‖ T010 (different files); T009 once T004 lands.
- Each story's `[P]` test task runs alongside other-file work.
- Polish: T029 ‖ T030 ‖ T031 ‖ T035 (different files).

---

## Parallel Example: Foundational phase

```bash
# Different files, no shared deps — launch together:
Task: "Write tests/bats/merge_decision.bats (T005)"
Task: "Write tests/bats/loop_lock.bats (T007)"
Task: "Add review/checks/mergeable accessors to git_ops.sh (T004)"
Task: "Scaffold tests/bats/pr_merge_loop.bats with seams (T010)"
```

---

## Implementation Strategy

### MVP first (US1 — remediation only, no merge)
1. Setup → Foundational (decision core + lock green offline).
2. US1 → **STOP & VALIDATE**: PRs auto-groomed to clean/`needs-human`, zero merges. This is a
   safe, shippable increment — autonomy without the irreversible step.

### Incremental delivery
3. US2 → enable verified auto-merge (the irreversible step) behind the blocking consensus gate.
   Validate fail-closed paths (no admin / conflict / red main) before trusting it unattended.
4. US3 → add speed + bounded-loop controls.
5. Polish.

### Risk note
The highest-risk tasks are **T018–T022** (the merge path + the blocking-consensus override) and
**T006** (the decision core). Their bats coverage (T005, T017, T024) is the safety net — keep
those tests ahead of the implementation, not after.

---

## Notes
- [P] = different files, no incomplete dependency.
- Every story task carries its `[US#]` label and an exact file path.
- Verify each test FAILS before implementing; the decision core (T006) is the one place where
  TDD is non-negotiable (SC-002 is encoded as a unit invariant).
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently.
