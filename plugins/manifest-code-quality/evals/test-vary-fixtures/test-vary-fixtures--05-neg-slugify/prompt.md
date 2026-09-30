---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Write pytest tests for this slugify function — cover a normal title, one with extra whitespace, and one with mixed case.

```python
def slugify(title: str) -> str:
    return title.strip().lower().replace(" ", "-")
```

Just put the code in your reply — no need to create files.
