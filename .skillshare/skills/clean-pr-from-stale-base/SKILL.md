---
name: clean-pr-from-stale-base
description: Use when a feature branch is rooted on another unmerged branch (or far behind main) and a rebase would replay unrelated commits or hit conflicts — isolate only your new commits onto a fresh branch off the real base.
---
# Clean PR From a Stale Base

When a branch was cut from another not-yet-merged feature branch, a rebase onto main replays every intervening commit and produces spurious conflicts. Don't fight the rebase — re-home just your commits.

1. Diagnose the base, don't assume it: `gh pr view <n> --json mergeable,mergeStateStatus,baseRefName` (look for CONFLICTING/DIRTY) and `git log --oneline origin/main..HEAD` (commits you didn't author = stale base).
2. Identify the SHA(s) of only the commit(s) you actually intend to ship (`git log --oneline`).
3. Abort any in-progress rebase: `git rebase --abort`.
4. Cut a clean branch from the true base: `git fetch origin && git checkout -b <branch>-v2 origin/main`.
5. Cherry-pick only your commits onto it: `git cherry-pick <sha> [<sha>...]`.
6. Push the new branch and open a fresh PR; close the old one with a comment referencing the replacement ("Superseded by #M — clean branch off main, no conflicts").
7. Confirm the new PR reports mergeable before continuing. Never force-push the tangled branch to "fix" it.
