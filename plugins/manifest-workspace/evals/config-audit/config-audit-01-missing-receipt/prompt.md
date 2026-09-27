---
max_turns: 25
timeout_seconds: 450
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Treat `./state` in the current directory as my `XDG_STATE_HOME` (export `XDG_STATE_HOME="$PWD/state"` for anything you run). No Manifest receipt has been written there. Audit my Manifest configuration for the Claude Code harness and tell me if anything has drifted.
