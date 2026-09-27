---
type: llm
weight: 1
---
Score 1 only if the answer recommends verifying the fix in an environment that lacks `jq`/`curl` (or a generally clean/stripped environment, e.g. a minimal container/CI image or a `PATH` without those tools) rather than only testing on a machine that already has them installed. Score 0 if no such verification is suggested.
