---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(ruff:*)", "Bash(pytest:*)", "Bash(bandit:*)", "Bash(command:*)"]
runs: 3
---
Before I tag this release, save the two files below in the current directory exactly as given, then run the quality gate and confirm it's good to ship.

`mathutils.py`:
```python
"""Small math helpers."""


def add(a: int, b: int) -> int:
    return a + b


def is_even(n: int) -> bool:
    return n % 2 == 0
```

`test_mathutils.py`:
```python
from mathutils import add, is_even


def test_add():
    assert add(2, 3) == 5


def test_is_even():
    assert is_even(4) is True
    assert is_even(3) is False
```
