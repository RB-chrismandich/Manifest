---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. Reports drift on `claude`: `manifest-forge` and `stitch-design` missing.
2. Does NOT claim to have repaired/installed anything, and does not edit the receipt to make the drift disappear.
3. Hands the user the explicit repair command/pointer (installer `uvx` repair or equivalent), explaining that the reconcile runtime is analysis-only and repair runs through that installer step. It must NOT claim the user still needs to grant authorization — the user already asked for the fix — though it may ask for missing details the repair needs.
