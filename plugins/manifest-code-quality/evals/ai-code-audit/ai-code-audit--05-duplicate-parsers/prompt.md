---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Agent, Read, Write, Grep, Glob, "Bash(mkdir:*)", "Bash(ls:*)", "Bash(grep:*)", "Bash(python3:*)", "Bash(node:*)", "Bash(git:*)"]
runs: 3
---
First save each file below into this workspace at the path given in its header comment, then run the audit against that local tree.

We've been adding report parsers fast this sprint. Can you audit these two for AI-generated issues before we add a third one?

```python
# reports/parse_csv.py
import math


def parse_csv_row(row: str) -> dict:
    """Parse "name,amount". Raises ValueError naming the row if it is malformed."""
    parts = row.strip().split(",")
    if len(parts) != 2 or not parts[0]:
        raise ValueError(f"expected 'name,amount', got {row!r}")
    try:
        amount = float(parts[1])
    except ValueError as exc:
        raise ValueError(f"amount is not a number in row {row!r}") from exc
    if not math.isfinite(amount):
        raise ValueError(f"amount must be finite in row {row!r}")
    return {"name": parts[0], "amount": amount}
```

```python
# reports/parse_export.py
import math


def parse_export_row(row: str) -> dict:
    """Parse "name,amount". Raises ValueError naming the row if it is malformed."""
    parts = row.strip().split(",")
    if len(parts) != 2 or not parts[0]:
        raise ValueError(f"expected 'name,amount', got {row!r}")
    try:
        amount = float(parts[1])
    except ValueError as exc:
        raise ValueError(f"amount is not a number in row {row!r}") from exc
    if not math.isfinite(amount):
        raise ValueError(f"amount must be finite in row {row!r}")
    return {"name": parts[0], "amount": amount}
```
