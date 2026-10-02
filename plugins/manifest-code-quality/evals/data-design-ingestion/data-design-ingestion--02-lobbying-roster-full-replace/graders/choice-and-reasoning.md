---
type: llm
weight: 1
---
Score 1 only if the answer recommends a full-window replace (delete the existing
rows / truncate, then insert the freshly fetched full set) wrapped in a single
transaction, justified by the feed re-publishing its complete current state each
call with no diff/version marker, AND guards against an empty/zero-row response
wiping the table (skip the delete/insert and keep the existing rows). Score 0 if
it recommends append-only inserts with a dedup id/upsert-by-id as the primary
strategy, or omits the empty-feed guard entirely. (Do not reward or require
bumping a freshness timestamp on an empty fetch.)
