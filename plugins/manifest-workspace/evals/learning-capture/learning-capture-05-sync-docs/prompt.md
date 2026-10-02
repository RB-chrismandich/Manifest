---
max_turns: 15
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Treat `./data` in the current directory as my `XDG_DATA_HOME` (export `XDG_DATA_HOME="$PWD/data"` for anything you run). Render my whole Manifest knowledge base (seed entries included) to a markdown doc at `./KNOWLEDGE_BASE.md`.
