---
max_turns: 10
timeout_seconds: 150
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
This function should return the average score but blows up with a TypeError. What's wrong and how do I fix it?

```python
def average(scores):
    total = sum(scores)
    return total / len(scores)

print(average(["10", "20", "30"]))
```
