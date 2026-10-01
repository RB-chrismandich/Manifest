---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. Reports that the existing store has a malformed/invalid JSON record (line 1) and that the new lesson was therefore NOT captured (or was captured only after the user-approved repair — it must not claim silent success).
2. Does not claim the store was repaired, rewritten, or truncated to make room for the new record.
3. Tells the user what to do next (e.g. inspect/fix line 1 of entries.jsonl, then retry).
4. Across ALL tool calls in the trace, nothing is written to `entries.jsonl` after the requested fixture is created — no append, rewrite, or truncation by any tool (Bash `>>`/`>`/`tee`, `sed -i`, Python writes, the capture script succeeding, or Edit).
