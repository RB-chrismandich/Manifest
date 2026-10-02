---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It says to check out the run's commit (headSha) and run the step's four commands locally in order, one at a time, to isolate which one fails.
2. It suggests matching CI's environment (Node version from the workflow, clean install via `npm ci`).
3. It does NOT guess a single culprit without reproduction or tell the user to just wait for logs.
