---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Recommends a way to move only the 2 commits onto main: `git rebase --onto main feat-a feat-b`, or cherry-picking the 2 commits onto a fresh branch from main.
2. Does NOT reframe the task as merging a stacked PR chain (no retarget-child/merge-parent-first choreography as the main answer).
