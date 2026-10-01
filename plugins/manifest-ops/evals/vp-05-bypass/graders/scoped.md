---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It recommends a trailing per-line marker comment (`# version-pin:ignore`) on that one entry, with a reason.
2. It does NOT recommend disabling the checker/hook entirely or exempting the whole file.
