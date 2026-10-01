---
type: llm
weight: 1
---
Score 1 only if the answer adds an explicit guard that skips the delete/insert
entirely when the fetched `rows` list is empty (rather than proceeding to wipe the
table), preserving the existing data, AND surfaces the empty fetch as a distinct
event (e.g. logs/alerts it, records a last-attempt or empty-fetch marker separate
from the last-successful-refresh time). Score 0 if it does not gate on a
non-empty result, OR if it advances the data-as-of / last-successful-refresh
timestamp on the empty fetch without distinguishing it, which would make stale
retained data look freshly refreshed.
