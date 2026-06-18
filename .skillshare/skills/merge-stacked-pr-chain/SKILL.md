---
name: merge-stacked-pr-chain
description: Use when merging a chain of stacked PRs (each based on the previous branch, not main) via the gh/glab CLI — `gh pr merge --delete-branch` on a parent CLOSES the dependent child instead of retargeting it; merge keeping the branch, retarget the child, then delete.
---
# Merge a Stacked PR Chain Safely

Distinct from `clean-pr-from-stale-base` (rebasing one branch onto a fresh base) and `reset-reapply-clean-pr` (untangling tangled history). This is the merge-time choreography for an already-open stack.

1. **Map the stack first.** `for n in <PRs>; do gh pr view $n --json number,baseRefName,headRefName; done`. Confirm the chain: A(base `main`) ← B(base A) ← C(base B) …
2. **Ensure CI runs on every PR before merging.** A workflow keyed `on: pull_request: branches: [main]` only triggers for PRs targeting `main`; stacked children targeting a non-main base show "no checks reported" and can't be gated. Drop the base filter (`on: pull_request:` with no `branches:`) so each story-PR is independently green.
3. **Merge bottom-up, one at a time.** For each parent: wait for green + `MERGEABLE`, then `gh pr merge <parent> --merge` **without** `--delete-branch`.
4. **Immediately retarget the child** onto the surviving base: `gh pr edit <child> --base main`; verify with `gh pr view <child> --json baseRefName`.
5. **Only then delete the merged parent branch:** `git push origin --delete <parent-branch>`. Order is the whole point — deleting before retargeting triggers the cascade.
6. **Recover a cascaded-closed child.** If you already deleted a base and GitHub auto-closed the child (a closed PR can't be retargeted or reopened while its base ref is gone): restore the ref with `git push origin <merged-sha>:refs/heads/<deleted-base>`, then `gh pr reopen <child>`, `gh pr edit <child> --base main`, then delete the temp ref.
7. **Let each retarget re-run CI** against its new base; wait for green before merging it.
8. **Finish clean.** Sync local `main` (`git checkout main && git pull`) and prune the merged local branches.
