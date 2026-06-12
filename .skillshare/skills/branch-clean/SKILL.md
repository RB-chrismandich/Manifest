---
name: branch-clean
description: >-
  Identify and safely prune stale git branches — merged into the default branch,
  tracking a deleted remote ([gone]), or stale beyond a threshold. Dry-run and
  local-only by default (remote deletion opt-in); never touches protected or
  checked-out branches.
---

# Branch Cleanup

Find local branches that are safe to delete and remove them with confirmation.
Groups candidates by reason and previews before doing anything destructive.

This skill is backed by `~/.claude/scripts/branch_clean.sh`. Protected globs and
the staleness threshold come from the `branch_clean` block of
`config/command_config.yml`.

## When to use

- Your local branch list has accumulated merged / abandoned branches.
- After merging several PRs, to clear out the merged source branches.
- To find branches whose remote was deleted (`[gone]`).

## Task

1. **Preview first** (dry-run is the default — deletes nothing):

   ```bash
   ~/.claude/scripts/branch_clean.sh
   ```

   Candidates are grouped by reason: **Merged into <default>**, **Gone upstream**,
   **Stale > Nd**. Protected and current branches are listed as never-deleted.

2. **Apply, with confirmation:**

   ```bash
   # Delete the local candidates (prompts for confirmation)
   ~/.claude/scripts/branch_clean.sh --apply

   # Also delete the matching remote branches (opt-in)
   ~/.claude/scripts/branch_clean.sh --apply --include-remote

   # Tune staleness / add protected patterns
   ~/.claude/scripts/branch_clean.sh --stale-days 60 --protect 'wip/*'
   ```

3. **Review the outcome.** Each deletion reports `deleted` or `FAILED`. A
   `FAILED` on a `[gone]` or `stale` branch usually means it has unmerged commits
   — the safe path (`git branch -d`) refuses to force-delete it. Delete it
   manually with `git branch -D <name>` only if you are sure the work is
   disposable.

## Safety guarantees

- **Local-only by default** (FR-016a): remote branches are deleted only with
  `--include-remote`.
- **Dry-run by default** (FR-018): nothing is deleted without `--apply` +
  confirmation (use `--yes` in non-interactive contexts).
- **Never touches** the default branch, configured protected globs, or the
  currently checked-out branch (FR-017).
- **Never force-deletes** unmerged branches via the default path (FR-020); such
  attempts fail safely and are reported, not swallowed (FR-019).
