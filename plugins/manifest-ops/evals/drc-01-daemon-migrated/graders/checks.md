---
type: regex
target: last_message
match: contains
flags: i
weight: 0.5
---
lsof -i ?:4000|launchctl
