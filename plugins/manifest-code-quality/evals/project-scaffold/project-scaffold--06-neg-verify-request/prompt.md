---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(ruff:*)", "Bash(pytest:*)", "Bash(command:*)"]
runs: 3
---
Save the two files below in the current directory exactly as given, then run our lint and test checks and tell me if this is good to merge.

`greet.py`:
```python
def greet(name):
    return f"Hello, {name}!"
```

`test_greet.py`:
```python
from greet import greet


def test_greet():
    assert greet("Ada") == "Hello, Ada!"
```
