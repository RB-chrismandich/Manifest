---
max_turns: 15
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Treat `./data` in the current directory as my `XDG_DATA_HOME` (export `XDG_DATA_HOME="$PWD/data"` for anything you run). We just hit the unquoted-shell-variable antipattern again in review. It's already a seed entry in my Manifest knowledge base — bump its occurrence count rather than adding a duplicate.
