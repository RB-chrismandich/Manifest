---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Security check on this — the LLM returns JSON describing a report to save:

```python
import json, os
OUT = "/var/app/reports"

def persist(llm_json: str):
    data = json.loads(llm_json)
    path = os.path.join(OUT, data["filename"])
    with open(path, "w") as f:
        f.write(data["content"])
```
The model is summarizing customer-submitted support tickets.
