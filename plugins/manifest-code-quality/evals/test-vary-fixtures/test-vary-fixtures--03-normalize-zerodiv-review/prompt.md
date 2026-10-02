---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Can you review this? It throws `ZeroDivisionError: float division by zero` in CI and I can't figure out why — the `normalize` function looks fine to me.

```python
def normalize(values):
    mean = sum(values) / len(values)
    stdev = (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5
    return [(x - mean) / stdev for x in values]

def test_normalize_centers_and_scales():
    data = [42.0] * 8
    result = normalize(data)
    assert result == [0.0] * 8
```
