---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Sanity check this CLI entry point for us — does `--help` actually work before any of our env/config requirements kick in?

```bash
#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF2'
Usage: sync-tool [--help] <source> <dest>
EOF2
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

: "${SYNC_TOKEN:?SYNC_TOKEN must be set}"
src="${1:?usage: sync-tool <source> <dest>}"
dest="${2:?usage: sync-tool <source> <dest>}"

echo "syncing $src -> $dest"
```
