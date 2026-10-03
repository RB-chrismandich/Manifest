---
type: regex
target: last_message
match: contains
flags: i
weight: 1
---
gh run view[^\n]*--log-failed|--log-failed
