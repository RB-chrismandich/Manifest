---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Provides a command that selects branches whose upstream is `[gone]` (e.g. `git for-each-ref --format '%(refname:short) %(upstream:track)'` or `git branch -vv | grep ': gone]'`).
2. Uses `git branch -d` (safe) in the one-liner, not `-D`, OR shows a dry-run listing step first and clearly caveats any `-D` variant.
3. Excludes the currently checked-out branch (feat/billing is not gone here anyway, but the answer does not delete main/current).
4. Suggests previewing the list before deleting.
