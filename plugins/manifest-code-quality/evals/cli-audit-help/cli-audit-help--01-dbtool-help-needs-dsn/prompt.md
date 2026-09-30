---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
We just added `--help` to `dbtool` but a new contributor says `dbtool --help` fails on their machine with a DB_DSN error instead of showing usage. Here's the script — what's wrong and how do we fix it properly?

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${DB_DSN:?DB_DSN must be set}"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/dbtool"
[[ -d "$config_dir" ]] || { echo "dbtool: config dir $config_dir not found; run 'dbtool init' first" >&2; exit 1; }

cmd="${1:-}"
case "$cmd" in
  --help|-h)
    cat <<'USAGE'
Usage: dbtool <command> [options]
Commands: query, migrate, init
USAGE
    exit 0
    ;;
  query) shift; echo "running query: $*" ;;
  migrate) shift; echo "running migrations" ;;
  init) mkdir -p "$config_dir"; echo "initialized $config_dir" ;;
  *) echo "dbtool: unknown command '$cmd'" >&2; exit 1 ;;
esac
```
