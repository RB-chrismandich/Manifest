---
type: llm
weight: 1
---
Score 1 only if the answer recommends an append-only write strategy (e.g.
`INSERT OR IGNORE` / `ON CONFLICT DO NOTHING`) keyed on a deterministic,
stable unique key — either a stable upstream identifier such as the award /
contract ID used as the UNIQUE or PRIMARY KEY, or a deterministic hash of the
stable identifying fields (with amounts formatted to fixed precision) — and
justifies it by the fact that awards are immutable once posted. Score 0 if it
recommends deleting/replacing the 7-day window on each run, keys on something
unstable (e.g. fetch time or row position), or gives no reasoning tied to the
immutable/append-only nature of the feed.
