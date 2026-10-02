---
max_turns: 5
timeout_seconds: 120
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Refactor this for readability — no behavior change:

```python
def ck(u,p,q):
    import hashlib
    s=u+"|"+p+"|"+"&".join(sorted(q))
    return "cache:"+hashlib.sha1(s.encode()).hexdigest()[:16]
```
It builds a Redis cache key for a GET request (user id, path, query params).
