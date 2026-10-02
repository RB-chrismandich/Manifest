---
type: llm
weight: 1
---
Score 1 only if the answer finds the `get_tickets` method / `POST
/v3/tickets/_mget` bulk path in the `ticketforge-python` SDK source excerpt —
which is absent from the published API docs — and recommends using it (directly
or via the SDK method) instead of looping `GET /v3/tickets/{ticket_id}` once per
id, chunking the ~900 ticket ids into calls of at most 300 (about 3 calls total).
Score 0 if the answer concludes no bulk endpoint exists because the public docs
don't show one, only proposes concurrency/caching/rate-limit workarounds while
keeping the per-ticket loop, or invents a bulk endpoint not present in either
excerpt.
