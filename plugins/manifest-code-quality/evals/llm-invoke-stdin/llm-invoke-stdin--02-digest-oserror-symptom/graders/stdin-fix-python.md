---
type: llm
weight: 1
---
Score 1 only if the proposed fix passes `prompt` via the `input=` parameter of `subprocess.run` (or an equivalent stdin pipe) while keeping the argv list short and fixed (e.g. `["claude", "-p", "<short instruction>"]`), rather than embedding the full prompt text in argv. Score 0 otherwise.
