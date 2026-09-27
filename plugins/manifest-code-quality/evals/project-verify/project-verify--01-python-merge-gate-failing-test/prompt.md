---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(ruff:*)", "Bash(pytest:*)", "Bash(bandit:*)", "Bash(command:*)"]
runs: 3
---
I'm about to merge this branch. Save the two files below in the current directory exactly as given, then run the quality gate on this project and tell me pass or fail before I merge.

`app.py`:
```python
def add(a, b):
    return a + b


def multiply(a, b):
    return a * b
```

`test_app.py`:
```python
from app import add, multiply


def test_add():
    assert add(2, 3) == 6


def test_multiply():
    assert multiply(3, 4) == 12
```
