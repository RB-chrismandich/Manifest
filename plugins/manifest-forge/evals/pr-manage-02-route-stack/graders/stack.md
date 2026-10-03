---
type: llm
focus: last_message
weight: 1
---
Pass only if ALL hold:
1. Merges #41 first, then #42.
2. Ensures #42 targets main before merging it, by either path:
   (a) merges #41 with its branch deleted (`--delete-branch` / auto-delete) and then verifies #42's base became main
       (GitHub retargets it automatically; e.g. `gh pr view 42 --json baseRefName`), retargeting by hand if it did not; or
   (b) keeps #41's branch, retargets #42 by hand (`gh pr edit 42 --base main`), and deletes the branch only afterwards.
3. Does NOT claim that deleting #41's merged branch closes #42.
