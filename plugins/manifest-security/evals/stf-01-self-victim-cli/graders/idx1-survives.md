---
type: regex
target: last_message
match: contains
flags: i
weight: 0.5
---
(surviv|kept|keep|valid|confirmed)[^\n]{0,120}(idx|index|#)\s*1|(idx|index|#)\s*1[^\n]{0,160}(surviv|kept|keep|valid|confirmed)
