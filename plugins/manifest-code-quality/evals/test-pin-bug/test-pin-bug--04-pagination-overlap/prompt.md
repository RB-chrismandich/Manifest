---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
QA reported that our paginated `/items` endpoint returns overlapping items — page 0 with page_size=3 returns 4 items, and the extra one shows up again as the first item of page 1. Root cause is `get_page()` computing `end = start + page_size + 1` instead of `start + page_size`. Fixing it properly needs a migration for cached page tokens, so it's parked for next quarter and I'm not changing the logic now.

```python
def get_page(items, page_num, page_size):
    start = page_num * page_size
    end = start + page_size + 1
    return items[start:end]
```

I want a regression test for `get_page(list(range(10)), 0, 3)` that won't need editing again the day we actually fix it. Can you write that pytest test?
