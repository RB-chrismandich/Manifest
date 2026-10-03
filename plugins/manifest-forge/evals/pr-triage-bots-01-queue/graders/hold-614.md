---
type: regex
target: last_message
match: contains
flags: i
weight: 1
---
#?614[^\n]{0,200}(hold|do not merge|don't merge|block|request changes|close)
