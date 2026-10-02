---
type: regex
target: trace
match: not_contains
weight: 0.5
---
ctx_(execute|batch_execute|search|execute_file|fetch_and_index)
