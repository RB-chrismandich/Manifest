---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our deploy script occasionally ships to a nonsensical "region" instead of failing loudly — audit it for silent-abort risks before we have to debug this live again.

`deploy.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

host="$1"

region="$(./fetch_region.py "$host")" || { echo "lookup: failed to resolve region for $host" >&2; exit 1; }

echo "deploying to region=$region"
```

`fetch_region.py`:

```python
#!/usr/bin/env python3
import sys, json

def lookup(host):
    data = {"web-1": "us-east-1", "web-2": "us-west-2"}
    return data[host]

try:
    print(lookup(sys.argv[1]))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(0)
```
