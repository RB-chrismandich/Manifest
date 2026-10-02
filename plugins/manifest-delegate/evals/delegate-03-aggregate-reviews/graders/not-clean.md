---
type: llm
focus: last_message
---
Pass only if ALL of these hold:
1. The answer does NOT declare the diff clean / safe to merge.
2. It keeps the claude job's failure (timeout) visible and does not count it as agreement or as a clean review.
3. It surfaces the codex medium finding (retry loop without max attempts) attributed to codex and/or job 91ab.
4. It surfaces the claude follow-up (re-run with a longer timeout) or equivalent next step.
