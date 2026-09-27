---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
In CI, `./release-cli --help` exits 1 with "missing API token file" — but it works fine on my laptop and nothing else changed. What's going on?

```bash
#!/usr/bin/env bash
set -euo pipefail

token_file="$HOME/.config/release-cli/token"
[[ -f "$token_file" ]] || { echo "release-cli: missing API token file at $token_file" >&2; exit 1; }
token="$(cat "$token_file")"

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: release-cli [--help] <env>"
  exit 0
fi

env_name="${1:?usage: release-cli <env>}"
echo "releasing to $env_name using token ${token:0:4}..."
```
