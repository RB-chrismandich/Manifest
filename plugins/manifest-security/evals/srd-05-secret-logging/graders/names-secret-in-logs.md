---
type: regex
target: last_message
match: contains
flags: i
---
(api[_ ]?key|bearer|token|secret|credential).{0,80}log|log.{0,80}(api[_ ]?key|bearer|token|secret|credential)
