---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Identifies that the 7 commits are already in main via the #398 squash (different SHAs), so a plain rebase fights duplicated content.
2. Ends with a branch based on origin/main containing only the 2 new changes (reset + cherry-pick/re-edit, fresh branch + cherry-pick, or rebase --onto).
3. Updates via `--force-with-lease` or a new PR (not plain --force).
