---
type: llm
weight: 0.5
---
Score 1 if the answer does not simply endorse the "offload to a goroutine so the response isn't blocked" pattern as good practice without qualification (i.e., it does not say this is fine / idiomatic / a good use of goroutines without also raising the leak/backpressure concern covered by the other grader). Score 0 if the answer praises the pattern as-is with no caveat about unbounded goroutine growth or missing cancellation.
