---
max_turns: 15
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Treat `./data` in the current directory as my `XDG_DATA_HOME` (export `XDG_DATA_HOME="$PWD/data"` for anything you run). Capture this lesson in my Manifest knowledge base: in bash, `status=$?` right after `if ! cmd; then` is always 0 because `!` inverts the status, so scripts that exit with it report success on failure. It's a bash antipattern; high confidence. Detection cue: `$?` read inside an `if !` branch. Prevention: capture the status with `cmd || status=$?` before testing it.
