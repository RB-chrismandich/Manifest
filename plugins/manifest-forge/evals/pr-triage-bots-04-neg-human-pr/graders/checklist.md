---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Provides a review checklist for retry/backoff logic (e.g. idempotency, max attempts, jitter, which errors are retried, timeouts).
2. Does NOT treat it as bot-PR triage (no duplicate-blob detection or bot dispositions).
