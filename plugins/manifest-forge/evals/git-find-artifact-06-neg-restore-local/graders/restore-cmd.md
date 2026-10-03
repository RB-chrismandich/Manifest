---
type: regex
target: last_message
match: contains
flags: i
weight: 1
---
git (restore\s+(--source\S*\s+)?(--staged\s+)?(--worktree\s+)?src/config\.ts|checkout\s+(HEAD\s+)?--\s+src/config\.ts)
