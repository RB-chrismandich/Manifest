---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This notifications module needs to keep running on Python 3.8 per our pyproject.toml (it ships inside an old support image we can't upgrade yet). Can you review it before we tag a release?

```toml
# pyproject.toml
[project]
name = "notifications"
version = "0.4.0"
requires-python = ">=3.8"
dependencies = [
    "httpx>=0.27",
]
```

```python
# notify.py
def send_digest(user_id: int, override_email: str | None = None, retry_count: int | None = None) -> bool:
    """Send the daily digest email; override_email lets ops redirect sends during incidents."""
    email = override_email or _lookup_email(user_id)
    attempts = retry_count if retry_count is not None else 3
    return _dispatch(email, attempts)


def _lookup_email(user_id: int) -> str:
    return f"user-{user_id}@example.com"


def _dispatch(email: str, attempts: int) -> bool:
    return attempts > 0
```
