---
type: regex
target: last_message
match: contains
flags: i
---
pwn[- ]?request|fork(ed)? (PR )?code.{0,60}secret|untrusted code.{0,60}(secret|token)
