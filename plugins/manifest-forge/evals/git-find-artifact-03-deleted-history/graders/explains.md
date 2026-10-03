---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Recognises a1b2c3d most likely deleted the file (a "cleanup" after the add) and that the content is readable from the parent of that commit or from d4e5f6a.
2. Gives a concrete `git show <sha>:<path>` (optionally after finding the exact path via `git show --stat` / `git ls-tree`).
3. Optionally offers restoring it with `git checkout <sha> -- <path>`; does not claim the content is unrecoverable.
