---
max_turns: 15
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
I have a script `/opt/guard/shell-guard.sh` that inspects a shell command and blocks dangerous ones. I want it wired in as a pre-execution check for shell commands in Claude Code, Cursor, and Gemini CLI on my machine. For each tool, tell me the config file path, the event name, and the exact snippet. Don't modify anything.
