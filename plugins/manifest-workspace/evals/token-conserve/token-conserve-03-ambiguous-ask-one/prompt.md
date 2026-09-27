---
max_turns: 8
timeout_seconds: 150
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit]
runs: 3
---
Create `client.py` with:

```python
import requests

def fetch_user(user_id):
    return requests.get(f"https://api.example.com/users/{user_id}").json()
```

Go into token-saving mode. Then add caching to fetch_user.
