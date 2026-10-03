---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Names the most likely cause as a stale/unmerged base (branch cut from another feature branch or outdated base), so extra commits are included.
2. Gives at least one concrete diagnostic command that shows which commits are not on main (e.g. `git log --oneline origin/main..HEAD`) or what the PR's base is (`gh pr view 88 --json baseRefName`).
3. Recommends moving only the 3 authored commits onto main (cherry-pick or rebase --onto) rather than resolving conflicts in commits the user didn't write.
