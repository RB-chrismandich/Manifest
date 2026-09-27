---
type: llm
weight: 1
---
Score 1 only if the answer explains using `terraform force-unlock <LOCK_ID>` (with the lock ID taken from the error message or the lock table/backend) to clear a stale lock, AND cautions to first confirm no other `apply`/`plan` is genuinely still running before forcing the unlock (to avoid concurrent-write state corruption). Score 0 otherwise.
