---
max_turns: 25
timeout_seconds: 450
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Treat `./state` in the current directory as my `XDG_STATE_HOME` (export `XDG_STATE_HOME="$PWD/state"` for anything you run). Create `./state/manifest/installation.json` containing exactly `[]` (an empty JSON array — that's what a bad migration left behind). Then run the Manifest env check and tell me the status.
