---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Proposes checking worktrees and all branches (e.g. `git worktree list`, `git branch -a`).
2. Proposes searching history across all refs for the filename or a glob of its stem (e.g. `git log --all -- '*retention*'`).
3. Proposes reading the file straight from the ref where it's found (`git show <ref>:<path>`) without first requiring a branch switch.
4. Does NOT simply conclude the file is missing or ask the user to paste/provide the spec as the first step.
