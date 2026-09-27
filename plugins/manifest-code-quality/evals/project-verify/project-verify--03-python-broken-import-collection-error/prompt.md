---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(ruff:*)", "Bash(pytest:*)", "Bash(bandit:*)", "Bash(command:*)"]
runs: 3
---
Here's a small data pipeline module I'm about to open a PR with. Save these three files in the current directory exactly as given, then sanity-check it's actually in working order before I do.

`helpers.py`:
```python
def clean(value):
    return value.strip().lower()
```

`pipeline.py`:
```python
from helpers import normalize


def run(values):
    return [normalize(v) for v in values]
```

`test_pipeline.py`:
```python
from pipeline import run


def test_run():
    assert run([" A ", " B "]) == ["a", "b"]
```
