---
type: regex
target: last_message
match: contains
flags: i
weight: 1
---
gh pr edit\s+12[^\n]*--add-reviewer\s+@?alice
