---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
This `round_price` function is supposed to round cents to the nearest dollar, but it truncates instead — `round_price(1995)` returns `19` when it should return `20`. Please fix the bug and add a test that locks in the correct rounded behavior going forward.

```python
def round_price(cents: int) -> int:
    return cents // 100
```

Just put the code in your reply — no need to create files.
