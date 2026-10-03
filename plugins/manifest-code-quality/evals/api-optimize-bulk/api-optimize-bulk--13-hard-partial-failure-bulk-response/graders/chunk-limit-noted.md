---
type: llm
weight: 0.5
---
Score 1 if the answer notes that the endpoint's 200-account_id-per-call limit
means 250 account_ids need at least 2 calls (e.g. chunking into groups of at
most 200) rather than one call covering all 250. Score 0 if the answer assumes
a single call can carry all 250 account_ids, or never mentions the per-call
limit.
