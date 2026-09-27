---
max_turns: 25
timeout_seconds: 450
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Treat `./state` in the current directory as my `XDG_STATE_HOME` (export `XDG_STATE_HOME="$PWD/state"` for anything you run). Create `./state/manifest/installation.json` containing exactly `{"harnesses": {"claude": "oops"}}` (a bad write left it like that). Then audit my Manifest config for Claude Code drift.
