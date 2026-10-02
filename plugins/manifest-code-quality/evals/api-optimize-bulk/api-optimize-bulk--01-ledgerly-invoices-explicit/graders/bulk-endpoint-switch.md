---
type: llm
weight: 1
---
Score 1 only if the answer recommends replacing the per-customer loop (one `GET /v1/customers/{id}/invoices` call per ID) with calls to the bulk endpoint `GET /v1/invoices?customer_ids=...` from the doc excerpt, explicitly stating the loop should stop issuing one request per customer. Score 0 if the fix keeps the per-customer loop as the primary approach (e.g. only suggests retries, caching, or concurrency without switching endpoints), or if it invents an endpoint not present in the excerpt.
