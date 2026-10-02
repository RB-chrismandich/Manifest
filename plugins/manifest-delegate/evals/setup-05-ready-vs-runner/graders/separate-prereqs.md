---
type: llm
focus: last_message
---
Pass only if ALL of these hold:
1. The answer says No (or "not by itself"): a `ready` backend only proves the external codex CLI is installed/authenticated/enabled.
2. The answer names at least one separate prerequisite that readiness does not prove: Claude Code discovering the `manifest-delegate:delegate-runner` agent, and/or the host being able to run that agent's configured model/tools.
3. The answer does not claim that `ready` alone makes native fan-out work end to end.
