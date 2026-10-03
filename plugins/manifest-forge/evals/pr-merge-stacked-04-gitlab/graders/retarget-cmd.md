---
type: regex
target: last_message
match: contains
flags: i
---
(glab mr (update|view)\s+!?13|target branch[^\n]{0,60}main)
