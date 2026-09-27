---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(ruff:*)", "Bash(pytest:*)", "Bash(bandit:*)", "Bash(command:*)"]
runs: 3
---
Quick check before I open the PR — save this as `stringutils.py` and `test_stringutils.py` in the current directory, then run the quality gate and tell me what it finds.

`stringutils.py`:
```python
import os
import re


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
```

`test_stringutils.py`:
```python
from stringutils import slugify


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
```
