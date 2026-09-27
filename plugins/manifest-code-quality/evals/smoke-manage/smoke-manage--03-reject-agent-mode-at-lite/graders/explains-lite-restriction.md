---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the answer explains that a `mode: agent` (LLM-driven/browser-use) UI step is not allowed at the `Lite` tier because the Lite PR gate must stay deterministic, and either refuses to add it at Lite or offers to add it at `Full` (or `Full+Extra`) instead. Score 0 if it silently adds the test at Lite tier, or gives no reason tied to the deterministic-gate rule.
