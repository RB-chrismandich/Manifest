---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Gives a direct command such as `gh pr merge 57 --delete-branch` (any merge strategy flag is fine).
2. Does NOT tell the user to avoid --delete-branch or to retarget child PRs; at most one short caveat about dependents is acceptable.
3. The answer is short and does not walk through a multi-PR stacked-merge procedure.
