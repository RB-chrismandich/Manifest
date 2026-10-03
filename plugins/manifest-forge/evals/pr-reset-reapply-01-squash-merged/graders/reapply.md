---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Explains the conflicts come from the old commits already being in main via the squash merge (not a stale base).
2. Ends with a branch based on origin/main containing ONLY the fix e9e9e9e (reset + cherry-pick, fresh branch + cherry-pick, or rebase --onto).
3. If it updates an existing remote branch, it uses `--force-with-lease` (not plain --force).
