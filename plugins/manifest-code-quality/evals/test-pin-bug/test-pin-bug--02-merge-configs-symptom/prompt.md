---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
We noticed `merge_configs` silently drops nested keys instead of deep-merging — e.g. our `db.port` setting vanishes whenever an override only touches `db.host`. Turns out it does a shallow `dict.update()`. Deep-merging is a bigger refactor we're deferring to next sprint, so I don't want to change the logic right now. Meanwhile I want a regression test for this call:

```python
def merge_configs(base: dict, override: dict) -> dict:
    result = dict(base)
    result.update(override)
    return result

base = {"db": {"host": "a", "port": 5432}}
override = {"db": {"host": "b"}}
```

I don't want the test to fail the day someone actually implements the deep merge. Can you write that test?
