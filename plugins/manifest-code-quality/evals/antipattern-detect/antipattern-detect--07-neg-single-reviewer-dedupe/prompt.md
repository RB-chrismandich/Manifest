---
max_turns: 10
timeout_seconds: 150
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
One reviewer left this comment on my PR: "this duplicates the date-formatting logic in utils/dates.py — can you just import that instead?" Here's the function:

```python
def format_order_date(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
```

And `utils/dates.py` already has:

```python
def format_date(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
```

Can you fix it per the review comment?
