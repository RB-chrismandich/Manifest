---
type: regex
target: last_message
match: contains
flags: i
weight: 1
---
git show\s+(a1b2c3d(\^|~1?)|d4e5f6a):\S*retention-audit
