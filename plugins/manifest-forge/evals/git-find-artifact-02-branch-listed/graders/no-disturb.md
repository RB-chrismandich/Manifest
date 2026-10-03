---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Reads the file via `git show spec/promote:<path>` (or origin/spec/promote), or first locates the exact path with `git ls-tree -r --name-only spec/promote`.
2. The primary recommended way to read the file does not touch the working tree. Mentioning `git switch`/`git stash`/`git checkout <branch> -- <path>` as an optional follow-up (e.g. for editing the file later) is fine; fail only if a branch switch or stash is presented as required to read it.
