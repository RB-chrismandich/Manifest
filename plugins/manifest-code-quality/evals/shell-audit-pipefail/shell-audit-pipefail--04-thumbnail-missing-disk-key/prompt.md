---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our metrics-shipper script blows up and kills the whole run whenever one host's `stats.json` is missing the `"disk"` section — older agents don't report it yet. Can you fix it so a host without disk stats just gets skipped instead of taking down the rest of the run?

```bash
#!/usr/bin/env bash
set -euo pipefail

for host_file in stats/*.json; do
  host="$(basename "$host_file" .json)"
  disk_pct="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["disk"]["used_pct"])' "$host_file")"
  echo "$host: disk ${disk_pct}%"
done
```
