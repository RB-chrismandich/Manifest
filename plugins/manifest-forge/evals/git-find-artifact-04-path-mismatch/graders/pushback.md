---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Does NOT agree that the file never existed.
2. Explains that searching the exact path misses a file committed under a different path/name, and proposes a basename/stem glob across all refs (e.g. `git log --all -- '*retention*'`) and/or `git ls-tree -r --name-only <branch> | grep -i retention` / `git worktree list`.
3. Says to report it as absent only after these broader searches come up empty.
