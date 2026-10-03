---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `fetch_balances` returns only
`resp.json()["balances"]` and silently discards `resp.json()["failed"]`, so any
account_id that comes back failed (closed/locked) is simply missing from the
result with no error, log, or signal to the caller — meaning the bulk response
was never checked to confirm it covers the full requested account_id universe.
The answer must recommend making partial failure caller-visible — raising an
error that includes the failed account_ids, or returning a typed result that
carries both `balances` and `failed` so the caller cannot treat an incomplete
map as full coverage — rather than assuming every requested account_id comes
back successfully. Logging `failed` without changing what the caller receives
does not suffice. Score 0 if the answer never mentions the `failed` field,
assumes all 250 accounts return successfully, treats log-only handling as
sufficient, or treats the function as correct as written.
