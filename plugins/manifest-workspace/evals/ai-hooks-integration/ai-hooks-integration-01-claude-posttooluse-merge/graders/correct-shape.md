---
type: llm
focus: {source: file, path: settings.json}
weight: 2
---
The file is Claude Code settings JSON. Pass only if ALL hold:
1. It is valid JSON.
2. `permissions.allow` still contains `Bash(npm test:*)`.
3. `hooks.PreToolUse` still contains the Bash matcher entry running `/opt/guard/block-rm.sh` (not removed, not duplicated).
4. `hooks.PostToolUse` exists and is an array of objects with a `matcher` that matches both Edit and Write (e.g. `Edit|Write`, `Edit|MultiEdit|Write`, or `*`), and a nested `hooks` array containing `{"type": "command", "command": ".../opt/fmt/prettier-hook.sh..."}`.
5. The new hook is NOT placed under PreToolUse and NOT as a flat `{"command": ...}` without the nested `hooks` array.
