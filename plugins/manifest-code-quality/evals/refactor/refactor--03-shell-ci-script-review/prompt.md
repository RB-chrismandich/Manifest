---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Here's a helper from our CI toolbox, `ci-run.sh` — can you refactor it for security and quality?

```bash
#!/usr/bin/env bash
run() {
  local cmd="$1"
  eval "$cmd"
}

run "$1"

rm -rf $WORKDIR/tmp/*
```
