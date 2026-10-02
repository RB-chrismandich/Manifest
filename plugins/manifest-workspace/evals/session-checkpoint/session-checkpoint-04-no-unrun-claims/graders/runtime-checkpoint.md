---
type: llm
focus: trace
---
Pass only if the trace shows the checkpoint was produced by the skill's runtime and not hand-written: a `session_continuity.py checkpoint --input ...` (or equivalent runtime) invocation that SUCCEEDED and printed the checkpoint path under `state/manifest/checkpoints/`, and nothing in the trace shows that file being created or overwritten by hand (Write/Edit, `echo`/`cat >`/`tee`, Python `open(...).write`). If the trace shows the file's permissions, they must be owner-only (e.g. `-rw-------`).
