---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our nightly status dashboard printed "ALL SYSTEMS GREEN" last night, but PagerDuty alerting was actually completely broken in that environment — it turns out the runner never had `PAGERDUTY_TOKEN` set. Here's the checker. Can you tell me why it didn't catch that, and how to fix it for good?

```python
import os
import requests

def check_pagerduty():
    token = os.environ.get("PAGERDUTY_TOKEN")
    if not token:
        return True  # nothing to check without a token
    resp = requests.get(
        "https://api.pagerduty.com/abilities",
        headers={"Authorization": f"Token token={token}"},
        timeout=5,
    )
    return resp.status_code == 200

def check_database():
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=5)
        conn.close()
        return True
    except Exception:
        return False

results = {
    "pagerduty": check_pagerduty(),
    "database": check_database(),
}

if all(results.values()):
    print("ALL SYSTEMS GREEN")
else:
    print("SYSTEM DEGRADED:", {k: v for k, v in results.items() if not v})
```
