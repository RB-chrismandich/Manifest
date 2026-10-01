---
max_turns: 15
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
My sidecar calls an upstream with a Bearer token from `UPSTREAM_TOKEN`. How do I write a pytest that proves the token can never leak to clients (response or logs) when the upstream fails?

```python
# sidecar/app.py
import json, logging, os, urllib.request
from flask import Flask, jsonify

app = Flask(__name__)
log = logging.getLogger("sidecar")
UPSTREAM = os.environ.get("UPSTREAM_URL", "https://api.internal.example/summary")

@app.get("/summary")
def fetch_summary():
    token = os.environ["UPSTREAM_TOKEN"]
    req = urllib.request.Request(UPSTREAM, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return jsonify(json.load(resp))
    except Exception:
        log.warning("upstream request failed")
        return jsonify(error="upstream error"), 502
```
