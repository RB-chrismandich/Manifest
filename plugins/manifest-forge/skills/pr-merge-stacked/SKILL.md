---
name: pr-merge-stacked
description: Use when merging stacked PRs via gh/glab — `gh pr merge --delete-branch` on a parent CLOSES the dependent child instead of retargeting it; merge keeping the branch, retarget the child, then delete.
---
# Merge a Stacked PR Chain Safely

Distinct from `pr-clean-base` (rebasing one branch onto a fresh base) and `pr-reset-reapply` (untangling tangled
history). This is the merge-time choreography for an already-open stack.

1. **Map the stack first.** GitHub:
   `for n in <PRs>; do gh pr view "$n" --json number,baseRefName,headRefName; done`.
   GitLab: `for n in <MRs>; do glab mr view "$n" --output json; done`. Confirm
   A(base `main`) ← B(base A) ← C(base B) …
2. **Ensure CI runs on every PR before merging.** A workflow keyed `on: pull_request:
   branches: [main]` only triggers for PRs targeting `main`; remove that base filter
   where every stacked child must be independently gated.
3. **Merge bottom-up, one at a time.** Wait for green and mergeability, then
   `gh pr merge <parent> --merge` or `glab mr merge <parent>`, **without**
   deleting the parent branch.
4. **Immediately retarget the child** onto the surviving base:
   `gh pr edit <child> --base main` or `glab mr update <child> --target-branch main`;
   then read it back using the same provider CLI.
5. **Only then delete the merged parent branch:** `git push origin --delete
   <parent-branch>`. Deleting first triggers the cascade.
6. **Recover a cascaded-closed child.** Restore the ref with `git push origin
   <merged-sha>:refs/heads/<deleted-base>`, then `gh pr reopen <child>` or
   `glab mr reopen <child>`, retarget it, then delete the temporary ref.
7. **Let each retarget re-run CI** against its new base; wait for green before merging it.
8. **Finish clean.** Sync local `main` (`git checkout main && git pull`) and prune merged branches.
