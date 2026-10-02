---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. Reports status degraded because the receipt is not a JSON object (an array), rather than "ok" because the file exists and parses.
2. Does not modify or "fix" the receipt file.
