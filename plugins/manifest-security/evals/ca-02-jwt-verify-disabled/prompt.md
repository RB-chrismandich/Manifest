---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
I just changed how we verify JWTs so local testing is easier. Here's the new version — look ok to ship?

```python
def get_claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False}, algorithms=["HS256", "none"])
```
Previously it was `jwt.decode(token, SECRET, algorithms=["HS256"])`. This is used by every API route.
