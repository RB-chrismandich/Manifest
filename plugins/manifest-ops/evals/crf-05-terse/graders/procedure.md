---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It says to get per-step (or per-job) conclusions from the CI API while the run is still in progress.
2. It says to pin the run's commit SHA.
3. It says to locate the failing step/job in the workflow file and run its commands locally.
