---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Names `~/.gemini/settings.json` (or project `.gemini/settings.json`) as the config file — not `~/.claude/settings.json` or a Cursor file.
2. Uses the Gemini CLI event `AfterTool` (not Claude's `PostToolUse`, not Cursor's event names).
3. Provides a JSON snippet with a `hooks` object keyed by `AfterTool`, containing an entry with a `matcher` targeting Gemini's shell tool (e.g. `run_shell_command`) and a command hook running `/usr/local/bin/notify-done`.
4. Does not claim that the answer requires installing a third-party wrapper because Gemini CLI lacks hooks.
