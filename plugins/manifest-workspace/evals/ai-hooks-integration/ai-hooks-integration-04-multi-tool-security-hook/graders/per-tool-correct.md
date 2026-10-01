---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Claude Code: `~/.claude/settings.json`, event `PreToolUse`, matcher `Bash`, nested `hooks: [{"type":"command","command":"/opt/guard/shell-guard.sh"}]`.
2. Cursor: `~/.cursor/hooks.json`, event `beforeShellExecution`, entry with `command: /opt/guard/shell-guard.sh`.
3. Gemini CLI: `~/.gemini/settings.json`, event `BeforeTool`, matcher targeting the shell tool (e.g. `run_shell_command`), with a nested `hooks: [{"type":"command","command":"/opt/guard/shell-guard.sh"}]` — an entry with no command hook (or an empty `hooks` array) fails.
4. Blocking works in EACH tool: the answer either gives a per-tool adapter/normalizer, or explicitly states that `shell-guard.sh` must emit each tool's own blocking response and spells out the contract — Claude: exit code 2 (or `hookSpecificOutput.permissionDecision: "deny"`); Gemini CLI: a BeforeTool deny decision; Cursor: a `permission: "deny"` / `continue: false` response. Registering the same script for all three without addressing the different blocking protocols fails (it would fail open in the tools whose protocol it doesn't speak).
5. Each tool's config is separate — it never tells the user to put one tool's hook into another tool's config file, or to reuse Claude's event names for Cursor/Gemini.
Minor formatting differences are fine; a wrong event name or wrong file for any tool is a fail.
