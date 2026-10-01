---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This started failing with `Argument list too long` once `huge_config.json` grew past a few hundred KB. What's the fix?

```bash
#!/usr/bin/env bash
set -euo pipefail

config="$(cat huge_config.json)"
docker run --rm -e CONFIG_JSON="$config" myimage:latest process
```
