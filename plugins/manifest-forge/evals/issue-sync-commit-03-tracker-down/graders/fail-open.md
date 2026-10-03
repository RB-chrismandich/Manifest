---
type: llm
focus: last_message
weight: 1
---
Pass if the answer says the sync must fail open: emit a warning and never block/fail the commit; it can self-heal on the next commit or a manual re-run.
