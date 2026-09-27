---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Can you punch up the `--help` text for this formatter with a short description and one usage example? Don't change any of the logic.

```bash
#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  -h|--help)
    echo "Usage: fmt-tool [--help] <file>"
    exit 0
    ;;
esac

file="${1:?usage: fmt-tool <file>}"
echo "formatting $file"
```
