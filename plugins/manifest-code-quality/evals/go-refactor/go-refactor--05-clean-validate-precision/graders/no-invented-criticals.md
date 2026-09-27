---
type: llm
weight: 1
---
This function is exported with a doc comment, uses `fmt.Errorf` for proper error wrapping, has no injection risk, no secrets, no concurrency, and no ignored errors. Score 1 only if the answer does NOT invent a Critical or High severity finding (e.g. does not claim a security vulnerability, race condition, or ignored error in this snippet). Minor/Low advisories (e.g. "add table-driven tests", "consider a stricter RFC 5322 check") are fine. Score 0 if any Critical/High finding is fabricated.
