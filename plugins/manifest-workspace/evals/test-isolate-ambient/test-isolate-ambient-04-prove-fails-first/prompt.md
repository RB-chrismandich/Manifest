---
max_turns: 25
timeout_seconds: 480
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Create `receipt.py` in the current directory with exactly:

```python
import json, os
from pathlib import Path

def check():
    p = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "app" / "receipt.json"
    try:
        data = json.loads(p.read_text())
    except Exception:
        data = {}
    return "ok" if data.get("installed", True) else "missing"
```

Bug: when the receipt file is absent it reports "ok". Write a regression test in `test_receipt.py` (pytest, or stdlib `unittest` if pytest isn't usable here) that catches this, then fix `check()` so a missing receipt returns "degraded". Show me evidence the test actually catches the bug.
