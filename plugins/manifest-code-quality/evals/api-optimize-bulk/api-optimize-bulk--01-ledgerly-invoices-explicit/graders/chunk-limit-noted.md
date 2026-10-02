---
type: llm
weight: 0.5
---
Score 1 if the answer accounts for the bulk endpoint's 500-customer-per-call limit when handling the ~1200 customer IDs — e.g. chunking them into groups of at most 500 and issuing a small number of bulk calls (about 3) instead of one call for everything. Score 0 if the answer assumes the bulk endpoint can return all 1200 customers in a single call, or never mentions the per-call limit at all.
