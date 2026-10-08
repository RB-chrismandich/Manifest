---
type: llm
focus: last_message
weight: 1
---
Pass only if the answer instructs the user to check out the CI run's exact `headSha` and execute the four `Build & test` commands locally in their workflow order, one at a time, to isolate the failure. It must match the workflow's Node 22 environment and use a clean `npm ci` install. It must not guess one command without reproduction or make waiting for logs the sole plan.
