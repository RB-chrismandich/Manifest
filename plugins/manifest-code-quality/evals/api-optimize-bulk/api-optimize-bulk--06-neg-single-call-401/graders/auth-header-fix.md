---
type: llm
weight: 1
---
Score 1 only if the answer identifies the missing `Bearer ` prefix in the `Authorization` header (per the doc excerpt) as the cause of the 401, and shows the corrected header as something like `f"Bearer {api_key}"`. Score 0 if the answer proposes a bulk/batch endpoint change or otherwise doesn't name the missing `Bearer` prefix as the fix (this snippet makes a single call, not a per-entity loop).
