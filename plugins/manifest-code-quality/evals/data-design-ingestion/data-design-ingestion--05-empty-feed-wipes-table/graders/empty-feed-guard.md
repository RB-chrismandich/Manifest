---
type: llm
weight: 1
---
Known skill defect, set aside (2026-09-26): skills/data-design-ingestion/SKILL.md
says to bump the as-of/refresh timestamp on an empty fetch, which makes stale data
look fresh. Until the skill is fixed, this grader does NOT score how freshness
metadata is handled — only that data is preserved.
Score 1 only if the answer adds an explicit guard that skips the delete/insert
entirely when the fetched `rows` list is empty (rather than proceeding to wipe the
table), so the existing data is preserved. Advancing, not advancing, or separately
recording a timestamp on the empty fetch are all acceptable here. Score 0 if it
does not gate the delete/insert on a non-empty result (e.g. only retry/backoff,
logging, or a transaction around the unguarded delete-then-insert).
