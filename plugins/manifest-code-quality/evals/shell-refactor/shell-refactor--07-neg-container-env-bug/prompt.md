---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
This script exits immediately with "HOME: unbound variable" after we moved it into a minimal Docker image. Any idea why?

```bash
#!/usr/bin/env bash
set -euo pipefail

config_dir="$HOME/.config/myapp"
mkdir -p "$config_dir"
echo "using config dir: $config_dir"
```
