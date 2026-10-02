---
type: llm
focus: trace
---
Pass only if ALL of these hold:
1. The trace shows an attempt to run the plugin's dispatcher (`delegate.py task ...`) — not a direct `codex exec`/`codex` CLI call.
2. That dispatcher command targets codex (`--backend codex`) and requests background mode (`--background`).
3. The command does NOT pass `--write` (the user asked that nothing be modified).
4. The task text is passed via a task file (`--task-file`) or stdin (`-`), or as a single properly quoted argument — not spliced unquoted into the shell command.
