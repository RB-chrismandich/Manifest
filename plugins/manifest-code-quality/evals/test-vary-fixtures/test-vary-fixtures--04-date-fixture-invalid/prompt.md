---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This baseline fixture for our anomaly detector blows up with `ValueError: day is out of range for month` when the test suite runs. Here's the fixture and the failing test:

```python
from datetime import date

def build_baseline(n_days):
    return [
        (date(2026, 2, i + 1), 40.0 + (0.5 if i % 2 else -0.5))
        for i in range(n_days)
    ]

def test_baseline_has_30_days():
    baseline = build_baseline(30)
    assert len(baseline) == 30
```

What's going on and how should I fix it?
