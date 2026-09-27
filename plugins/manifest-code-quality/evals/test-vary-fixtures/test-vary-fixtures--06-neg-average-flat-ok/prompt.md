---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Write a unit test for this function:

```python
def average_response_time(samples: list[float]) -> float:
    return sum(samples) / len(samples)
```

Test it with `[200, 200, 200, 200, 200]` — it should return `200`.

Just put the code in your reply — no need to create files.
