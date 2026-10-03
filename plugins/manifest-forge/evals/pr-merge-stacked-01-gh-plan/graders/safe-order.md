---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Merges bottom-up: #41 first, then #42, then #43.
2. After each merge, verifies the next PR's base is now main (e.g. `gh pr view 42 --json baseRefName`, or the
   automatic_base_change event) instead of assuming it; retargets by hand (`gh pr edit 42 --base main`) if it is not.
3. Does NOT claim that deleting feat-a after #41 merges closes #42 (GitHub retargets it). Keeping feat-a is also
   acceptable if the plan then retargets #42 manually before deleting it.
4. If the plan squash- or rebase-merges, it rebases the child onto main to drop the parent's original commits
   (e.g. `git rebase --onto origin/main <old-feat-a-sha> feat-b`); with merge commits no rebase is needed.
5. Makes sure CI actually runs against the new base after the retarget (e.g. adds `edited` to the workflow's
   pull_request types, pushes/rebases the child, or closes+reopens it) and waits for that run to go green before
   merging; it must not assume the retarget alone re-runs CI.
