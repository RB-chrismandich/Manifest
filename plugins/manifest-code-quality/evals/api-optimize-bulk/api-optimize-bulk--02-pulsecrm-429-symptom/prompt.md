---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
We keep getting `429 Too Many Requests` syncing contacts overnight. We have about 1500 contact IDs to sync. Here's the relevant PulseCRM doc section and the sync code — what should we do?

```
GET /api/v2/contacts/{contact_id}
  Single contact record.

POST /api/v2/contacts/batch
  Body: {"ids": ["id1", "id2", ...]}
  Returns up to 1000 contact records per call.

Rate limit: 100 requests/minute per API key (applies to both endpoints above).
```

```python
import requests

def sync_contacts(contact_ids, api_key):
    contacts = []
    for cid in contact_ids:
        resp = requests.get(
            f"https://api.pulsecrm.example/api/v2/contacts/{cid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        contacts.append(resp.json())
    return contacts
```
