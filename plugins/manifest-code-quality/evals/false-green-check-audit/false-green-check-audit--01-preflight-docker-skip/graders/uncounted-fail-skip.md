---
type: llm
weight: 1
---
Score 1 only if the answer identifies that the "FAIL: database unreachable" branch (and/or the AWS "SKIP" branch) never increments `total` or any failure/skip counter, so `pass -eq total` still holds and "ALL CHECKS PASSED" prints even though the database check failed or AWS was never verified. Score 0 if the answer does not identify that a FAIL or SKIP outcome is invisible to the final summary.
