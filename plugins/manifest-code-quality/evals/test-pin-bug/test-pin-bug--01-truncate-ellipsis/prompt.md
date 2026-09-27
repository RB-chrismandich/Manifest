---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
This truncate helper is supposed to cap strings at `limit` characters *including* the ellipsis, but it just slices to `limit` and then appends `"..."`, so the result can run longer than `limit`. I know about this — it's a known bug, ticket filed, but I'm not touching the logic in this PR. I just want a pytest test that locks in today's behavior for `truncate_with_ellipsis("hello world", 5)` without blowing up the suite the day someone actually fixes the length math.

```python
def truncate_with_ellipsis(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "..."
```

What test should I add?
