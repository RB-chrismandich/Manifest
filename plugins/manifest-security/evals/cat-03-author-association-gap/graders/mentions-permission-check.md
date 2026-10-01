---
type: regex
target: last_message
match: contains
flags: i
weight: 0.5
---
write[- ]access|permission level|collaborators/.{0,20}permission|/permission
