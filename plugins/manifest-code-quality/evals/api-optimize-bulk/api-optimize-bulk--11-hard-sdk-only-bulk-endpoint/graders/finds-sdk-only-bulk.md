---
type: llm
weight: 1
---
Score 1 only if the answer finds the `get_tickets` method / `POST
/v3/tickets/_mget` bulk path in the `ticketforge-python` SDK source excerpt —
which is absent from the published API docs — and recommends using it (directly
or via the SDK method) instead of looping `GET /v3/tickets/{ticket_id}` once per
id, chunking the ~900 ticket ids into calls of at most 300 (about 3 calls
total). Because the SDK comment marks the path internal-only and not yet GA,
the recommendation must be conditioned on verifying the endpoint works — e.g. a
minimal authenticated probe against the real API before adopting it, or
explicitly flagging it as a candidate pending verification — rather than an
unconditional "use this GA endpoint." Score 0 if the answer concludes no bulk
endpoint exists because the public docs don't show one, only proposes
concurrency/caching/rate-limit workarounds while keeping the per-ticket loop,
invents a bulk endpoint not present in either excerpt, or recommends the
endpoint unconditionally as fully supported with no verification caveat.
