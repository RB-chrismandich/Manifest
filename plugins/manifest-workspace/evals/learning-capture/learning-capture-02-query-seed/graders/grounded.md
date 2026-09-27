---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Cites at least one of the seed entries ANTI-021 ("Catch-log-return-undefined (swallowed error)") or ANTI-022 ("Catch-and-discard without propagation or fallback") by ID.
2. Summarizes what the entry says (swallowed/discarded errors without propagation or fallback) without inventing IDs that do not exist.
3. Does not add a new record to the store in response to a read-only question.
