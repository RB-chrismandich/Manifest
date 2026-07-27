---
name: pr-reset-reapply
description: When a feature branch's history is tangled with already-merged commits, reset to the default branch and reapply only the net diff as one clean PR
---
# Reset-and-Reapply for a Clean PR

Trigger: a follow-up fix lives on a branch whose earlier commits were already squash-merged into main, so `git rebase
origin/main` conflicts or the PR shows overlapping/duplicated history.

If the mess comes from the branch being cut from a stale/unmerged base (not from already-merged commits), use
pr-clean-base instead.

1. Confirm the situation: `git fetch origin` then `git log --oneline origin/main..<branch>` and `git log --oneline
   origin/main -5`. If the branch's "new" commits duplicate content already in main, a rebase will fight you.
2. Capture the net change you actually want to keep (the file diffs from the follow-up fix) before touching history —
   read the relevant files or stash a diff.
3. Reset the branch onto the merged base: `git reset --hard origin/main`. The branch now equals main; the tangled
   history is gone.
4. Reapply ONLY the net diff — re-edit the files (or `git cherry-pick <sha>` of the single clean commit) so the working
   tree contains exactly the intended change and nothing already in main.
5. Re-run any pre-deploy validation (dry-run, verify script) before committing, since the reset reverted everything
   including unrelated prior edits.
6. Commit as one focused, reviewable commit and `git push --force-with-lease`.
7. Open a fresh PR if the previous one was already merged; never reopen merged history. Verify with
   `~/.claude/scripts/git_ops.sh pr-view <n> --json state,commits` that the new PR contains only the intended
   commit(s).
8. Never `git rebase -i` interactively in a non-interactive agent shell and never force-push without
   `--force-with-lease`.
