---
type: regex
target: last_message
match: contains
flags: i
weight: 1
---
git (restore\s+((?![^\n|;&]*--staged)|(?=[^\n|;&]*--worktree))(?:--source(?:\s+|=)\S+\s+|--(?:staged|worktree)\s+)*src/config\.ts|checkout\s+(HEAD\s+)?--\s+src/config\.ts)
