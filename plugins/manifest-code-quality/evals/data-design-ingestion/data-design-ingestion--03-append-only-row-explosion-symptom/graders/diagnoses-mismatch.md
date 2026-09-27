---
type: llm
weight: 1
---
Score 1 only if the answer diagnoses the root cause as a design mismatch: this
feed is re-published-in-full and subject to amendment, so append-only + hash
dedup is the wrong ingestion model for it (any corrected field changes the hash
and produces an unbounded stream of "new" rows for the same underlying filing).
It must recommend switching to a full-window replace (delete the affected
window/period, then insert the fresh set, in one transaction) rather than
append-only. Score 0 if it only suggests tweaking the hash formula, excluding
`amount` from the key, or otherwise patches the dedup key without recommending
the append-only-to-full-replace design change.
