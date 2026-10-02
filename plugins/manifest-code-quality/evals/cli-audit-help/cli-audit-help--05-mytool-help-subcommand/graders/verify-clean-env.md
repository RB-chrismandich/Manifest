---
type: llm
weight: 1
---
Score 1 only if the answer recommends verifying the fix in a clean/fresh environment where no state file exists yet — e.g. an empty `HOME`/`MYTOOL_STATE` pointing at a nonexistent path, or a fresh install before `mytool init` — not just re-running on a machine that already has state. Score 0 if no such verification is suggested.
