---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. Identifies that the receipt is malformed/unparseable JSON.
2. Treats that as drift / repair required — not as a clean or converged install, and not as "claude has manifest-forge installed".
3. Does not silently rewrite or "fix" the receipt file itself.
