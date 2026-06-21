# Contract — `pr_merge_loop.sh` (orchestration) & `loop_lock.sh`

Repo script conventions apply: `set -euo pipefail`, `err()` for all error/warning output, a
`--help` handler (≤15 lines, exit 0). Side-effecting `gh` calls live here (behind injectable
seams for tests); the *decision* lives in `merge_decision.sh`.

## `pr_merge_loop.sh list-managed [--json]`
List open PRs whose author is in the automation allowlist (FR-013). Skips human authors.
**Out**: JSON array `[{number, author, head_ref, state}]`. **Exit**: `0` ok; `3` none managed.

## `pr_merge_loop.sh signals <pr> [--json]`
Recompute the signals object (the `merge_decision.sh decide` input) for one PR by calling the
R1–R4 read-only commands. **Out**: the signals JSON. **Exit**: `0`; `4` on auth failure
(fail-closed — caller treats as `reviewer_error`).

## `pr_merge_loop.sh address-cycle <pr>`
Run one revision cycle: `/address-pr-comments` → `/verify` → `/pr-review`; push fixes;
increment `revisions_used`. **Exit**: `0` cycle ran; `2` nothing to address.

## `pr_merge_loop.sh merge <pr>`
Pre-flight admin/protection check (R1) → `gh pr merge --squash --admin --delete-branch`.
**Refuses** unless the caller already holds the lock and `merge_decision` returned `merge`.
Fail-closed: no admin / `enforce_admins` / `required_signatures` / merge-queue → exit `9`
(→ caller labels `ready-to-merge`). **Exit**: `0` merged; `9` cannot-merge-fail-closed;
`2` conflict→human.

## `pr_merge_loop.sh post-merge-check`
Read `main` HEAD check-runs (R3). **Exit**: `0` green; `10` red (→ caller `halt`s); `8` pending.

## `pr_merge_loop.sh empty-run <get|incr|reset>`
Manage `consecutive_empty` (FR-018a) in the state dir. `get` prints the count; loop stops at ≥5.

## `loop_lock.sh <acquire|release|is-held> <pr>`
Label-based lock (`loop-active`) + local `flock` (R4). `acquire` exit `0` got it / `1` held by
another. `release` is idempotent and also invoked from the caller's `trap … EXIT`.
**Stale reclaim**: a `loop-active` older than `LOOP_LOCK_STALE_MIN` (default 15) is reclaimable.

## Cross-cutting
- **`--apply` flag** (loop-level): off = dry-run (compute decisions, print, mutate nothing);
  on = perform labels/edits/merges. Mirrors `auto-dev-issue-prep`/repo norm.
- **Seams for tests**: `PR_MERGE_LOOP_GH_CMD`, `PR_MERGE_LOOP_REVIEW_CMD`, `..._VERIFY_CMD`
  override the external calls so `pr_merge_loop.bats` runs fully offline against fixtures.
- **Redaction**: every comment body / annotation / audit line passes `audit_log.sh redact`.
- **Audit**: each `merge`/`hand-human`/`halt`/`address` appends one `audit_log.sh` record (FR-021).
