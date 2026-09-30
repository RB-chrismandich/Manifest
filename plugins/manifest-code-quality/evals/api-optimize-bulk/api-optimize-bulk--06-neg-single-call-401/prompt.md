---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This call keeps returning 401 even though the API key is definitely correct. Here's the relevant part of the Billwise docs and my code — what am I missing?

```
All requests require the header:
  Authorization: Bearer <API_KEY>
Requests with a missing or malformed Authorization header return 401 Unauthorized
with body {"error": "invalid_token"}.
```

```python
import os
import requests

resp = requests.get(
    "https://api.billwise.example/v1/account",
    headers={"Authorization": os.environ["BILLWISE_API_KEY"]},
)
print(resp.status_code, resp.json())
```
