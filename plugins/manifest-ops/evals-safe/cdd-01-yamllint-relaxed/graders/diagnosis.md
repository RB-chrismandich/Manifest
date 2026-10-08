---
type: llm
focus: last_message
weight: 1
---
Pass only when the answer explains that the workflow's `-d relaxed` option supplies its own yamllint rules instead of using the repository `.yamllint`, so CI and the local command enforce different policies. It must frame this as configuration divergence rather than 14 defective YAML lines. It must recommend making the workflow use the repository config (for example, remove the preset or pass `.yamllint` explicitly), or deliberately updating the checked-in policy if relaxed defaults are intended. Rewrapping all flagged lines must not be the primary recommendation.
