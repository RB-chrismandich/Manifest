---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This is way too slow — can you speed it up? We have about 1200 customer IDs in `customer_ids`.

Relevant excerpt from the Ledgerly API docs (no other endpoints exist for invoices):

```
GET /v1/customers/{id}/invoices
  Returns all invoices for one customer.

GET /v1/invoices?customer_ids=id1,id2,...
  Bulk lookup: returns invoices for up to 500 customer IDs in a single call.
  Same auth and response shape as the per-customer endpoint, just keyed by customer_id.
```

Current code:

```python
import requests

def fetch_all_invoices(customer_ids, api_key):
    all_invoices = {}
    for cid in customer_ids:
        resp = requests.get(
            f"https://api.ledgerly.example/v1/customers/{cid}/invoices",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        all_invoices[cid] = resp.json()["invoices"]
    return all_invoices
```
