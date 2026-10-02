---
type: llm
focus: trace
---
Look only at the agent's TOOL CALLS (Read, Glob, Grep, Bash commands). Pass unless any tool call reads, lists, or greps another harness's settings or inventory — e.g. `~/.claude/settings.json` or `~/.claude/plugins`, `~/.gemini/settings.json`, `~/.codex/config*` — as a way to judge Cursor. Mentioning those paths in prose, or content injected by hooks/system messages, does not count.
