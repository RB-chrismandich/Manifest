---
type: llm
weight: 1
---
Score 1 only if the answer recommends switching to `POST /api/v2/contacts/batch` with an `ids` array (the bulk endpoint from the doc excerpt) instead of looping over `contact_ids` one at a time, and notes chunking the ~1500 IDs into groups of at most 1000 per call (about 2 calls total) to respect the batch endpoint's per-call limit. Score 0 if the answer keeps the per-contact loop as the recommended approach and only proposes rate-limit workarounds (delays, retries, backoff) without switching to the batch endpoint.
