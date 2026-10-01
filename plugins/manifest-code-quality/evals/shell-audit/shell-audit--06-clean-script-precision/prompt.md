---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Run a shell audit on this before I commit it — any silent-abort or control-flow risks under strict mode?

```bash
#!/usr/bin/env bash
set -euo pipefail

err() { echo "backup.sh: $*" >&2; }

src="${1:?usage: backup.sh <src> <dest>}"
dest="${2:?usage: backup.sh <src> <dest>}"

if [[ ! -d "$src" ]]; then
  err "source $src is not a directory"
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)" || { err "date failed"; exit 1; }
count=0
while IFS= read -r -d '' f; do
  cp -p "$f" "$dest/" </dev/null
  count=$((count + 1))
done < <(find "$src" -type f -name '*.conf' -print0)

echo "backed up $count files at $stamp"
exit 0
```
