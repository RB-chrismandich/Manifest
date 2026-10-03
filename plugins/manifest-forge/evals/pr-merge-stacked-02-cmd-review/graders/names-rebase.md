---
type: regex
target: last_message
match: contains
flags: i
weight: 0.5
---
rebase\s+(--onto|-i)|--onto|merge\s+commit
