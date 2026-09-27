---
max_turns: 4
timeout_seconds: 120
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Why does this crash with FileNotFoundError on a fresh machine?

```python
from pathlib import Path
REPORTS = ["daily", "weekly", "monthly"]
def init_dirs():
    for r in REPORTS:
        (Path("/tmp/app/out") / r).mkdir()
```
