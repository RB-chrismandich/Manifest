---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. Does NOT open a PR, push, commit, or edit any installed skill tree.
2. Explains that the bundle's apply path is analysis-only/degraded — opening a review PR goes through a separate explicit repository workflow — without claiming the user still needs to grant authorization (the user already asked to apply and open the PR).
3. Asks only for the details that workflow is missing — at minimum the target repository (forge/branch are a plus) — rather than re-asking for permission.
