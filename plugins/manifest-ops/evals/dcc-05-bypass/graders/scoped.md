---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It recommends an inline suppression on the `user: root` line (or within the migrate service block) that names DC-007 specifically, with a comment giving the reason.
2. It warns against a bare ignore (suppresses all rules on the line) and against `ignore-file` (exempts the whole file).
