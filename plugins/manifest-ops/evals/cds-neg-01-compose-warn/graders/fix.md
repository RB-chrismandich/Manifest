---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It identifies this as Compose's own interpolation: `DB_PASSWORD` is not defined in `.env` (next to the compose file) or the shell environment.
2. It tells the user to define it (in `.env`, exported, or via `--env-file`), optionally with `${DB_PASSWORD:?}` to fail loudly.
3. It does NOT claim the app performs its own second-layer substitution here.
