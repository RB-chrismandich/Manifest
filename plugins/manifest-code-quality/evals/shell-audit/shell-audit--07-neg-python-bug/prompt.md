---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Why does this return the wrong answer for `[3, 1, 2]`?

```python
def second_largest(xs):
    xs.sort()
    return xs[len(xs) - 1]
```
