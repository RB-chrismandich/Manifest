---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
I'm getting `AttributeError: 'RiskSnapshot' object has no attribute
'backlog_ratio'`. A teammate added the field on their branch but it never made it
into the dataclass definition on `main` after the merge. Here's the current class
on `main` — what do I need to add?

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class RiskSnapshot:
    ticker: str
    debt: float
    backlog: float
```
