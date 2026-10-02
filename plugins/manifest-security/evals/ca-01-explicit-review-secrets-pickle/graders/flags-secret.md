---
type: regex
target: last_message
match: contains
flags: i
---
hard-?coded.{0,40}(key|secret|credential)|API_KEY.{0,80}(env|secret manager|vault)
