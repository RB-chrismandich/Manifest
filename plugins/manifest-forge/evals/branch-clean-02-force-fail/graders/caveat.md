---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Explains that [gone] means the remote branch was deleted, not that the work was merged (e.g. it may have been squash-merged or abandoned), so unmerged commits could be lost.
2. Advises checking what would be lost first (e.g. `git log main..feat/login` or checking the PR was squash-merged) before `git branch -D`.
3. On remotes: says remote deletion is a separate, opt-in step (and notes the remote for feat/login is already gone); does not push-delete anything by default.
