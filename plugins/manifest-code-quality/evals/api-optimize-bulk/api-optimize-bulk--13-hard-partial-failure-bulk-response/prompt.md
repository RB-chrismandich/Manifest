---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Switched our nightly reconciliation to the bulk balances endpoint like you
suggested last time — much faster. We have 250 account_ids. Here's the current
code and the doc section for the endpoint, can you double check it before I
ship it?

```
POST /v1/accounts/balances
  Body: {"account_ids": ["id1", "id2", ...]}  (max 200 account_ids per call)
  Response: {
    "balances": {"<account_id>": {"available": <number>, "currency": "<str>"}, ...},
    "failed": [{"account_id": "<str>", "reason": "<str>"}]
  }
  An account_id may come back in `failed` instead of `balances` (e.g. account
  closed mid-cycle, temporary lock). Failed ids are NOT retried automatically.
```

```python
import requests

def fetch_balances(account_ids, api_key):
    resp = requests.post(
        "https://api.acctstream.example/v1/accounts/balances",
        json={"account_ids": account_ids},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    return resp.json()["balances"]
```
