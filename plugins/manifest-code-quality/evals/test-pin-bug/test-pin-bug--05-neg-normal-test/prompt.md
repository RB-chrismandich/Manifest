---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Can you write a pytest unit test for this function? Just want normal coverage, nothing fancy.

```python
def is_valid_slug(value: str) -> bool:
    return bool(value) and value == value.lower() and " " not in value
```

Cover a valid slug like `"my-post-title"` and an invalid one like `"My Post"`.

Just put the code in your reply — no need to create files.
