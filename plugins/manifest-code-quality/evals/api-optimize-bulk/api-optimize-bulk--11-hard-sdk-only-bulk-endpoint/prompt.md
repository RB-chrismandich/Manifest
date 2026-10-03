---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This nightly sync of ~900 ticket IDs is painfully slow. Here's the entire
"Tickets" section of TicketForge's published API reference (that's genuinely
everything it says about reading tickets), and separately the relevant excerpt
from the official `ticketforge-python` SDK source on GitHub, in case it's
useful. What would you change?

Published API docs:
```
GET /v3/tickets/{ticket_id}
  Returns a single ticket with full history.

(No bulk or multi-ticket read endpoint is documented in the public API
reference.)
```

`ticketforge/client.py` (official SDK, from the GitHub repo):
```python
class TicketForgeClient:
    def __init__(self, api_key):
        self.api_key = api_key

    def get_ticket(self, ticket_id):
        return self._get(f"/v3/tickets/{ticket_id}")

    def get_tickets(self, ticket_ids):
        # Internal-only bulk path, not yet promoted to the public docs
        # (GA planned Q3). Accepts up to 300 ids per call.
        return self._post("/v3/tickets/_mget", json={"ids": ticket_ids})["tickets"]

    def _get(self, path):
        ...

    def _post(self, path, json):
        ...
```

Our sync code (plain `requests`, not using the SDK):
```python
import requests

def fetch_tickets(ticket_ids, api_key):
    tickets = []
    for tid in ticket_ids:
        resp = requests.get(
            f"https://api.ticketforge.example/v3/tickets/{tid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        tickets.append(resp.json())
    return tickets
```
