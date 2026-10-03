---
type: llm
focus: last_message
weight: 1
---
Pass if the answer uses `gh api graphql` querying `reviewThreads` (with `isResolved`) and handles pagination (e.g. `--paginate` with `pageInfo { hasNextPage endCursor }` / `after:` cursor) so >100 items are all fetched.
