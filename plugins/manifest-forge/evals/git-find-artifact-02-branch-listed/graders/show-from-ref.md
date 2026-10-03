---
type: regex
target: last_message
match: contains
flags: i
weight: 1
---
git show\s+(origin/)?spec/promote:\S*promote-plan\.md
