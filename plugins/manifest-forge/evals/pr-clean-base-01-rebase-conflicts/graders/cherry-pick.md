---
type: regex
target: last_message
match: contains
flags: i
---
cherry-pick[^\n]*f00d00[12]|rebase\s+--onto\s+origin/main\s+ab12cd3
