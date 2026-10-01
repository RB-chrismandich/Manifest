---
type: regex
target: last_message
match: contains
flags: i
---
request[_ ]?id|generic (error|message)|opaque
