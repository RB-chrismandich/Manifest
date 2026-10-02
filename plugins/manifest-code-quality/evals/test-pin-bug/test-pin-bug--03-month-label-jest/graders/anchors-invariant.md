---
type: llm
focus: last_message
weight: 1
---
Score 1 only if, separate from the tolerant month check, the answer also asserts an invariant true under both the buggy and fixed versions — e.g. that the year segment is exactly `"2026"` (checked on its own, such as splitting on `"/"` and asserting the second part equals `"2026"`, or a regex like `/\/2026$/`) — as a distinct assertion from the month alternation. Score 0 if there is no separately-checked invariant, or it is merely the same alternation restated.
