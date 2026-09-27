---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Please security-review this before I open the PR:

```python
import subprocess, yaml
from flask import request

@app.post("/convert")
def convert():
    spec = yaml.load(request.data, Loader=yaml.Loader)
    out = subprocess.check_output(f"pandoc -f {spec['from']} -t {spec['to']} in.md", shell=True)
    return out
```
