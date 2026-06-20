# Quickstart — Autonomous PR Lifecycle & Merge Loop

> Prereqs: `gh` authenticated with an **admin** account on the repo (the merge bypass needs it);
> the #360 verification gate present; `/address-pr-comments`, `/pr-review`, `/verify` available.

## 1. Dry-run a single PR (safe — mutates nothing)

```bash
# Compute the signals and the decision without acting
configs/claude/scripts/pr_merge_loop.sh signals <PR> --json \
  | configs/claude/scripts/merge_decision.sh decide
# → {"action":"merge|revise|wait|update-branch|hand-human|halt", "reason":"...", "label":...}
```

This is the fastest way to see *why* a PR would or wouldn't merge — every clear-condition is in
the signals JSON.

## 2. List what the loop considers "managed"

```bash
configs/claude/scripts/pr_merge_loop.sh list-managed --json   # automation-authored PRs only
```
Human-authored PRs are absent by design (FR-013).

## 3. Verify the safety invariants offline (no network)

```bash
bats tests/bats/merge_decision.bats     # every decision-table row + SC-002 invariants
bats tests/bats/loop_lock.bats          # acquire/release/contention
bats tests/bats/pr_merge_loop.bats      # orchestration via injected seams
```

## 4. Run the loop

```bash
# Dry-run end-to-end (decisions + would-be actions, no mutations):
/loop /auto-issue-dev          # the extended skill; --apply OFF by default in dry-run

# Live (performs merges with admin bypass) — only when you intend autonomous merges:
/loop /auto-issue-dev --apply
```

The loop self-paces (acts the moment a PR is actionable), caps each run at ~10 min, processes
items one merge at a time, and **stops after 5 consecutive empty runs**. It **halts** if a merge
turns `main` CI red.

## 5. Observe

```bash
tail -n 20 "$AUDIT_FILE"                      # the audit log audit_log.sh appends to (per-PR action, revisions, consensus, outcome)
gh pr list --label needs-human               # parked for a human (with reasons in comments)
gh pr list --label ready-to-merge            # verified but the loop lacked merge authority
```

## What you should see
- A clean, green automation PR → `MERGED` to main, branch pruned, one audit line.
- A PR with a failing check → up to 3 revision cycles, then merged or `needs-human`.
- A PR with a human "request changes" or `hold` label → never merged; `needs-human`.
- A merge that reddens `main` → loop **HALTED**, offending PR recorded; no further merges until
  you clear it.
