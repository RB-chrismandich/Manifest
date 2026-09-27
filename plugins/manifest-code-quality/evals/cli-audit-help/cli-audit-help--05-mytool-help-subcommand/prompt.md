---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
New users can't get `mytool help` (or `mytool --help`) to work before they've run `mytool init` — both just error out about a missing state file. Here's the script, what's broken?

```bash
#!/usr/bin/env bash
set -euo pipefail

state_file="${MYTOOL_STATE:-$HOME/.local/state/mytool/state.json}"
[[ -f "$state_file" ]] || { echo "mytool: no state file at $state_file, run 'mytool init'" >&2; exit 1; }

case "${1:-}" in
  --help|-h)
    echo "Usage: mytool [--help] <command>"
    exit 0
    ;;
esac

cmd="${1:?usage: mytool <command>}"
case "$cmd" in
  help) echo "Usage: mytool [--help] <command>" ;;
  sync) echo "syncing using $state_file" ;;
  *) echo "mytool: unknown command '$cmd'" >&2; exit 1 ;;
esac
```
