---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It explains exit 137 = SIGKILL, typically the OOM killer / memory limit on the runner.
2. It gives concrete remedies (reduce test parallelism/workers, cap memory, larger runner, find the memory hog).
3. It does NOT generate a new CI pipeline.
