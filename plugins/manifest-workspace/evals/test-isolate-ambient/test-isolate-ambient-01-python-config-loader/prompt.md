---
max_turns: 25
timeout_seconds: 480
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Create `configload.py` in the current directory with exactly:

```python
import json, os
from pathlib import Path

def load_config():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / "mytool" / "config.json"
    if not path.exists():
        return {"status": "degraded", "reason": "config missing"}
    return {"status": "ok", **json.loads(path.read_text())}
```

Write tests for `load_config` in `test_configload.py` (pytest, or stdlib `unittest` if pytest isn't usable here) and run them. I want these tests to be trustworthy in CI and on any dev laptop.
