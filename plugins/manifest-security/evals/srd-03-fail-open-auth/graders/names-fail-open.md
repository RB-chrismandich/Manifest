---
type: regex
target: last_message
match: contains
flags: i
---
fail[- ]?open|auth(entication|orization)? bypass|bypass
