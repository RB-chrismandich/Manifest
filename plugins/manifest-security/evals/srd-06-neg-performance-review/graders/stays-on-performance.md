---
type: llm
focus: last_message
---
- Identifies the N+1 query problem caused by dropping `select_related("product")` and accessing `o.product` in a loop.
- Recommends restoring `select_related` (or equivalent prefetch).
- Does NOT pad the answer with a security review (no source→sink vulnerability section, no severity-rated security findings).
Pass only if all three hold.
