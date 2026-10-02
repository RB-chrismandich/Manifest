---
type: llm
focus: trace
weight: 2
---
Judge the agent's answer across ALL of its assistant messages (the final message may only say "the script above"). Pass only if ALL hold:
1. Provides a shell script that runs `black --check .` and exits non-zero when it fails.
2. Says it goes in `.git/hooks/pre-commit` (and needs to be executable), or equivalently configures the pre-commit framework.
3. Does NOT reframe this as an AI coding tool hook (no Claude `PreToolUse`/settings.json, Cursor hooks.json, Gemini settings, or OpenCode plugin).
