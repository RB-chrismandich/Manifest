---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(ruff:*)", "Bash(pytest:*)", "Bash(command:*)"]
runs: 3
model: sonnet
---
Save the two files below in the current directory exactly as given, then run our lint and test suite and tell me if this is safe to ship.

`inventory.py`:
```python
def in_stock(count):
    return count > 0
```

`test_inventory.py`:
```python
from inventory import in_stock


def test_in_stock():
    assert in_stock(5) is True
    assert in_stock(0) is False
```
