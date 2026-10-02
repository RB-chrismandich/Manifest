---
type: llm
weight: 1
---
Score 1 only if the answer identifies that the code deletes the entire 30-day
window and then inserts only the single capped API response (`limit=500`), so
filings beyond that page are permanently lost — a real data-loss bug — AND its fix
does BOTH of: (1) switch to append-only ingestion with a deterministic dedup id and
`INSERT OR IGNORE`/upsert (never deleting), justified by Form 4 filings being
immutable history; and (2) paginate until the feed is exhausted (follow the
cursor/offset until an empty or short page), so records beyond the first 500 are
ever fetched. Score 0 if either part is missing (append-only alone still never
fetches page 2+; pagination alone keeps the destructive delete-then-insert).
