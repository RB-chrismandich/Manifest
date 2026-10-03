---
type: llm
weight: 0.5
---
Score 1 if the answer accounts for the bulk method's 300-id-per-call limit when
handling the ~900 ticket ids (e.g. chunking into groups of at most 300, about 3
calls). Score 0 if the answer assumes all ~900 ids can be sent in a single call,
or never mentions the per-call limit at all.
