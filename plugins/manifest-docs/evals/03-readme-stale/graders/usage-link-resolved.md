---
type: llm
focus: trace
---
Judge the final repository state from the trace. Pass if the final README.md does NOT link to docs/USAGE.md, OR the run created docs/USAGE.md with real content. Fail if README.md still links docs/USAGE.md and that file was never created.
